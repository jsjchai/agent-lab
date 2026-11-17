#!/usr/bin/env python3
"""m06 · RAG 与知识问答 —— 对应文档 §8（Milvus 的本地替代）。

文档 §8 的基本流程在这里完整实现：

    文档 -> 解析清洗 -> Chunk -> Embedding -> 索引（本地 numpy，生产用 Milvus）
    问题 -> ACL 过滤 -> 混合检索（向量 + BM25）-> Rerank
         -> 证据片段与引用 -> LLM 回答 -> 引用校验 / 无依据拒答

工程规则（文档 §8）逐条落地：
1. 检索阶段执行租户 + 文档 ACL 过滤，不只靠 Prompt 保密。
2. 索引记录向量模型与维度，不同模型/维度不能混用。
3. 保留 doc_id / version / 段落来源。
4. 引用必须回溯到实际检索片段。
5. 无证据问题明确拒答。

运行（离线）：
    ../../.venv/bin/python m06_rag.py
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from common.llm import LLM, _tokenize_zh, describe, embed_model_name
from common.security import SecurityContext

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "data" / "knowledge"

# 疑问/功能词：不参与相关性判定，避免「是什么」这类通用词让任何问题都命中
_STOPWORDS = {
    "什么", "是什", "么", "的", "吗", "如何", "怎么", "哪些", "有", "多少",
    "请问", "是", "了", "和", "与", "吗？", "？", "什么？", "基本", "一下",
}


def _content_tokens(text: str) -> list[str]:
    return [t for t in _tokenize_zh(text) if t not in _STOPWORDS]


# --------------------------------------------------------------------------- 解析与切片
def parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    meta, body = {}, text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    meta["orgs"] = [o for o in meta.get("orgs", "").split(",") if o]
    return {"meta": meta, "body": body}


def chunk_doc(doc: dict) -> list[dict]:
    """按 ## 标题切片，保留来源标题。"""
    meta = doc["meta"]
    sections = re.split(r"\n##\s+", doc["body"])
    chunks = []
    for i, sec in enumerate(sections):
        sec = sec.strip()
        if not sec:
            continue
        title = sec.splitlines()[0].lstrip("# ").strip()
        chunks.append({
            "chunk_id": f"{meta['doc_id']}#{i}",
            "doc_id": meta["doc_id"],
            "version": meta.get("version", "1"),
            "tenant": meta["tenant"],
            "orgs": meta["orgs"],
            "doc_title": meta.get("title", ""),
            "section": title,
            "text": sec,
        })
    return chunks


# --------------------------------------------------------------------------- BM25
class BM25:
    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.corpus = corpus_tokens
        self.N = len(corpus_tokens)
        self.avgdl = sum(len(d) for d in corpus_tokens) / max(self.N, 1)
        self.df: dict[str, int] = {}
        for doc in corpus_tokens:
            for t in set(doc):
                self.df[t] = self.df.get(t, 0) + 1

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = []
        for doc in self.corpus:
            dl = len(doc)
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t in query_tokens:
                if t not in tf:
                    continue
                idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a @ b  # 向量已归一化


def rrf(rank_lists: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion：融合多路检索排名。"""
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for pos, idx in enumerate(ranks):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return scores


# --------------------------------------------------------------------------- 索引
class KnowledgeIndex:
    def __init__(self, llm: LLM):
        self.llm = llm
        self.chunks: list[dict] = []
        self.vectors: np.ndarray | None = None
        self.bm25: BM25 | None = None
        self.embed_model = embed_model_name()
        self.dim = 0

    def build(self, docs_dir: Path = KNOWLEDGE_DIR) -> None:
        self.chunks = []
        for path in sorted(docs_dir.glob("*.md")):
            self.chunks.extend(chunk_doc(parse_doc(path)))
        texts = [c["text"] for c in self.chunks]
        vecs = self.llm.embed(texts)
        self.dim = len(vecs[0])
        self.vectors = np.array(vecs, dtype=np.float32)
        self.bm25 = BM25([_content_tokens(t) for t in texts])

    def _acl_ok(self, chunk: dict, ctx: SecurityContext) -> bool:
        return chunk["tenant"] == ctx.tenant_id and bool(set(chunk["orgs"]) & set(ctx.org_ids))

    def retrieve(self, ctx: SecurityContext, query: str, k: int = 3) -> list[dict]:
        # ACL 过滤在检索阶段（文档规则 1）
        allowed = [i for i, c in enumerate(self.chunks) if self._acl_ok(c, ctx)]
        if not allowed:
            return []
        qvec = np.array(self.llm.embed([query])[0], dtype=np.float32)
        vec_scores = cosine(self.vectors[allowed], qvec)
        bm_scores = self.bm25.scores(_content_tokens(query))
        bm_allowed = [bm_scores[i] for i in allowed]

        # 相关性门槛：无内容关键词重叠且向量相似度过低 => 视为无证据（支撑「无依据拒答」）
        relevant = [j for j in range(len(allowed)) if bm_allowed[j] > 0.0 or vec_scores[j] > 0.25]
        if not relevant:
            return []
        allowed = [allowed[j] for j in relevant]
        vec_scores = vec_scores[relevant]
        bm_allowed = [bm_allowed[j] for j in relevant]

        vec_rank = [allowed[i] for i in np.argsort(-vec_scores)]
        bm_rank = [allowed[i] for i in np.argsort(-np.array(bm_allowed))]
        fused = rrf([vec_rank, bm_rank])

        # Rerank：关键词重叠启发式（生产用 bge-reranker 等交叉编码器）
        qtokens = set(_content_tokens(query))
        def rerank_score(i: int) -> float:
            overlap = len(qtokens & set(_content_tokens(self.chunks[i]["text"])))
            return fused.get(i, 0.0) + 0.01 * overlap

        ranked = sorted(fused, key=rerank_score, reverse=True)[:k]
        return [self.chunks[i] for i in ranked]

    def answer(self, ctx: SecurityContext, query: str, k: int = 3) -> dict:
        evidences = self.retrieve(ctx, query, k)
        if not evidences:
            return {"answer": "无法确认：知识库中没有找到相关依据。", "citations": [], "retrieved": []}

        blocks = "\n".join(f"【片段 {c['chunk_id']} | {c['doc_title']}·{c['section']}】\n{c['text']}" for c in evidences)
        messages = [
            {"role": "system", "content": "你是教学知识问答助手。只能依据给定证据片段回答，引用格式为 chunk_id。无依据则拒答。只输出 JSON：{answer, citations}。"},
            {"role": "user", "content": f"问题：{query}\n\n证据：\n{blocks}"},
        ]
        valid_ids = {c["chunk_id"] for c in evidences}

        def validate(data: dict) -> str | None:
            if "answer" not in data or "citations" not in data:
                return "缺少 answer/citations"
            if not set(data["citations"]).issubset(valid_ids):
                return "引用了未检索到的片段"
            return None

        result = self.llm.chat_json(messages, validate=validate)
        result["retrieved"] = [c["chunk_id"] for c in evidences]
        return result


# --------------------------------------------------------------------------- 评测问题集
EVAL_QUESTIONS = [
    # (问题, 用户, 期望命中的doc_id列表, 是否可答)
    ("活动时长有什么规定？", "u1", ["doc-rules"], True),
    ("主讲人数量有要求吗？", "u1", ["doc-rules"], True),
    ("如何查询轮转计划？", "u1", ["doc-rotation"], True),
    ("创建教学活动的流程是什么？", "u1", ["doc-rules"], True),
    ("文档入库的流程是什么？", "u3", ["doc-kb-manual"], True),
    ("量子力学的基本原理是什么？", "u1", [], False),
    ("今天食堂吃什么？", "u1", [], False),
]


def evaluate(index: KnowledgeIndex) -> dict:
    from common.security import authenticate

    recall_hits, mrr_sum, answerable, citation_ok, refusal_ok, refusals = 0, 0.0, 0, 0, 0, 0
    for query, user, want_docs, answerable_q in EVAL_QUESTIONS:
        ctx = authenticate(user)
        retrieved = index.retrieve(ctx, query, k=3)
        got_docs = [c["doc_id"] for c in retrieved]
        if answerable_q:
            answerable += 1
            hit = any(d in got_docs for d in want_docs)
            recall_hits += hit
            for rank, d in enumerate(got_docs, 1):
                if d in want_docs:
                    mrr_sum += 1.0 / rank
                    break
            ans = index.answer(ctx, query)
            citation_ok += bool(ans["citations"]) and set(ans["citations"]).issubset(set(ans["retrieved"]))
        else:
            refusals += 1
            ans = index.answer(ctx, query)
            refusal_ok += (not ans["citations"]) and ("无法确认" in ans["answer"])
    return {
        "Recall@3": round(recall_hits / max(answerable, 1), 3),
        "MRR": round(mrr_sum / max(answerable, 1), 3),
        "引用准确率": round(citation_ok / max(answerable, 1), 3),
        "无依据拒答率": round(refusal_ok / max(refusals, 1), 3),
    }


def demo() -> None:
    from common.security import authenticate

    print(f"【m06 RAG】{describe()}  embed={embed_model_name()}")
    index = KnowledgeIndex(LLM())
    index.build()
    print(f"  索引：{len(index.chunks)} 个片段，维度 {index.dim}")

    ctx = authenticate("u1")
    print("\n  u1(t1) 问「活动时长有什么规定？」：")
    ans = index.answer(ctx, "活动时长有什么规定？")
    print("   ", ans["answer"][:80])
    print("    引用:", ans["citations"])

    print("\n  ACL 测试：u1(t1) 能否检索到 t2 的知识库手册？")
    docs = {c["doc_id"] for c in index.retrieve(ctx, "文档入库的流程是什么？", k=5)}
    print("    检索到的文档:", docs, "-> 含 t2 手册?", "doc-kb-manual" in docs)

    print("\n  评测指标：", evaluate(index))


def selftest() -> None:
    from common.security import authenticate

    index = KnowledgeIndex(LLM("mock"))
    index.build()
    u1, u3 = authenticate("u1"), authenticate("u3")

    # ACL：u1 检索不到 t2 文档
    assert all(c["tenant"] == "t1" for c in index.retrieve(u1, "文档入库", k=5))
    # u3 只能检索 t2
    assert all(c["tenant"] == "t2" for c in index.retrieve(u3, "文档入库", k=5))
    # 可答问题有合法引用
    ans = index.answer(u1, "活动时长有什么规定？")
    assert ans["citations"] and set(ans["citations"]).issubset(set(ans["retrieved"]))
    # 无依据拒答
    ans = index.answer(u1, "量子力学的基本原理是什么？")
    assert not ans["citations"] and "无法确认" in ans["answer"]
    # 指标达标
    metrics = evaluate(index)
    assert metrics["Recall@3"] >= 0.8 and metrics["无依据拒答率"] == 1.0


if __name__ == "__main__":
    demo()
