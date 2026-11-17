# 06 · RAG 与知识问答

> 对应源文档 §8 · 代码模块 [`m06_rag.py`](../m06_rag.py) + [`data/knowledge/`](../data/knowledge/) · 运行：`../../.venv/bin/python m06_rag.py`

## 一、这是什么 / 为什么重要

RAG（检索增强生成）让 Agent 基于**自己的知识库**回答，而不是凭模型记忆瞎编。源文档 §8 的流程：

```
文档 → 解析清洗 → Chunk → Embedding → 索引
问题 → ACL 过滤 → 混合检索(向量+关键词) → Rerank → 证据片段与引用
     → LLM 回答 → 引用校验 / 无依据拒答
```

Teaching 场景用它做「教学知识问答」（活动规则、轮转计划、操作手册）。核心工程要求：
**检索阶段就做权限过滤**（不只靠 prompt 保密）、**引用必须回溯真实片段**、**无依据明确拒答**。
本模块用 numpy 本地索引替代 Milvus，把整条链路落成可运行代码。

## 二、核心概念详解

### 文档解析与 Chunk
`parse_doc` 解析 frontmatter 元数据（doc_id/version/tenant/orgs/title）+ 正文；
`chunk_doc` 按 `##` 标题切片，每片保留来源标题。Chunk 粒度影响检索精度。

### Metadata 与 ACL
每个 chunk 带 `tenant`（租户）和 `orgs`（组织）。检索时 `_acl_ok` 过滤：
`chunk.tenant == ctx.tenant_id 且 chunk.orgs 与 ctx.org_ids 有交集`。**权限在检索阶段执行**。

### Embedding 与向量检索
`LLM.embed` 把文本转向量（mock 用哈希词袋 256 维；真实用 bge-m3 1024 维）。
`cosine` 算相似度（向量已归一化，点积即余弦）。

### BM25 关键词检索
经典词频-逆文档频率打分。本项目用字符 bigram 切词（适配中文），`_content_tokens` 去掉疑问/功能词
（什么/是/的/吗…），避免「是什么」让任何问题都命中。

### Hybrid Search 与 RRF
向量检索 + BM25 各出一路排名，用 **RRF（Reciprocal Rank Fusion）** 融合：
`score(d) = Σ 1/(k + rank_i(d))`，k=60。两路互补：向量抓语义，BM25 抓精确词。

### Rerank
对融合结果重排。本项目用关键词重叠启发式（`fused + 0.01*overlap`）；生产用 bge-reranker 交叉编码器。

### Citation 与拒答
回答必须引用实际检索到的 chunk_id；无证据（retrieve 返回空）则拒答「无法确认」。

### Index Version
索引记录向量维度 `dim`；不同模型/维度不能混用。相关性门槛按 dim 区分（见下）。

## 三、代码实现解析

### retrieve：ACL + 相关性门槛 + 混合检索 + 重排

```python
def retrieve(self, ctx, query, k=3):
    # 1. ACL 过滤（检索阶段，文档规则 1）
    allowed = [i for i,c in enumerate(self.chunks) if self._acl_ok(c, ctx)]
    if not allowed: return []
    # 2. 向量 + BM25 打分
    vec_scores = cosine(self.vectors[allowed], qvec)
    bm_allowed = [self.bm25.scores(_content_tokens(query))[i] for i in allowed]
    # 3. 相关性门槛：无关键词重叠且向量过低 => 无证据（支撑拒答）
    vec_thr = 0.25 if self.dim <= 256 else 0.5     # mock 哈希 vs 真实 bge-m3
    relevant = [j for j in range(len(allowed)) if bm_allowed[j] > 0 or vec_scores[j] > vec_thr]
    if not relevant: return []
    # 4. RRF 融合两路排名
    fused = rrf([vec_rank, bm_rank])
    # 5. Rerank：关键词重叠启发式
    ranked = sorted(fused, key=lambda i: fused[i] + 0.01*overlap(i), reverse=True)[:k]
    return [self.chunks[i] for i in ranked]
```

**为什么这样写**：
- ACL 在最前，无权限文档根本不参与打分。
- 相关性门槛区分 mock/真实：bge-m3 给无关文档也有 ~0.3-0.4 相似度，门槛提到 0.5 才能干净拒答。
- 关键词重叠为主判据，向量兜底语义匹配。

### answer：证据块 + 引用归一化 + 拒答

```python
def answer(self, ctx, query, k=3):
    evidences = self.retrieve(ctx, query, k)
    if not evidences:
        return {"answer": "无法确认：知识库中没有找到相关依据。", "citations": [], "retrieved": []}
    blocks = "\n".join(f"【片段 {c['chunk_id']} | {c['doc_title']}·{c['section']}】\n{c['text']}" for c in evidences)
    # prompt 给 example_id 示范引用格式
    result = self.llm.chat_json(messages, validate=validate)
    ...

def validate(data):
    # 归一化引用：小模型可能输出 "chunk_id:doc-rules#1"，正则提取规范 id
    for c in raw_cites:
        m = re.search(r"doc-[\w-]+#\d+", str(c))
        if m and m.group(0) in valid_ids: cleaned.append(m.group(0))
    data["citations"] = cleaned
```

**为什么这样写**：引用必须 ⊆ 实际检索片段（`valid_ids`），小模型加前缀/格式漂移用正则纠正，
杜绝「引用了没检索到的片段」。无证据直接拒答，不让模型编。

## 四、工程要点与常见坑

| 现象 | 原因 | 对策 |
|---|---|---|
| 无权限文档被检索到 | 只在 prompt 说保密 | 检索阶段 `_acl_ok` 过滤 |
| 无关问题也命中 | 疑问词「是什么」匹配 | `_content_tokens` 去停用词 |
| bge-m3 无关文档误检索 | 语义模型基础相似度偏高 | 门槛按 dim 区分（0.25/0.5） |
| 引用格式漂移 | 小模型加 `chunk_id:` 前缀 | 正则提取规范 `doc-xxx#N` |
| 引用了没检索的片段 | 模型幻觉引用 | 校验 ⊆ valid_ids |
| 无依据硬答 | 模型编造 | retrieve 空 → 明确拒答 |
| 换向量模型结果乱 | 维度/模型混用 | 索引记录 dim，门槛适配 |

## 五、验收与测试

`selftest()` 断言：

```python
# ACL：u1(t1) 检索不到 t2 文档
assert all(c["tenant"]=="t1" for c in index.retrieve(u1, "文档入库", k=5))
# 可答问题有合法引用
ans = index.answer(u1, "活动时长有什么规定？")
assert ans["citations"] and set(ans["citations"]).issubset(set(ans["retrieved"]))
# 无依据拒答
ans = index.answer(u1, "量子力学的基本原理是什么？")
assert not ans["citations"] and "无法确认" in ans["answer"]
# 指标达标
assert metrics["Recall@3"] >= 0.8 and metrics["无依据拒答率"] == 1.0
```

`evaluate()` 用 `EVAL_QUESTIONS` 算 Recall@3 / MRR / 引用准确率 / 拒答率。mock 实测全 100%。

## 六、与其他模块的关系

- 用 [03 模型接入](03-模型接入与流式接口.md) 的 `LLM.embed`/`chat_json`。
- ACL 用 [07 安全](07-安全治理与人工确认.md) 的 `SecurityContext`。
- 引用校验复用 [01](01-LLM基础与结构化输出.md) 的 validate 契约。
- 被 [08 评测](08-评测与质量门禁.md) 的知识问答类用例覆盖。
- 知识文档在 [`data/knowledge/`](../data/knowledge/)（含租户/组织元数据）。

## 七、动手练习与延伸

1. 给 `data/knowledge/` 加一篇 t2 文档，用 u1 提问，验证检索不到（ACL）。
2. 把 `vec_thr` 真实模式改回 0.25，问「量子力学」，观察误检索（再改回）。
3. 接真实 bge-m3 + 7B（`TEACHING_LLM=openai`），跑 `evaluate` 对比 mock 指标。

## 参考

- 源文档 §8「RAG 与 Milvus」
- [Milvus 文档](https://milvus.io/docs)、[Ragas RAG 评测](https://docs.ragas.io/)
- 项目内：[`m06_rag.py`](../m06_rag.py)、[07 安全](07-安全治理与人工确认.md)、[08 评测](08-评测与质量门禁.md)
