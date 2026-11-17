"""统一 LLM 适配层 —— 对应文档 §3 LLM 基础 与 §5 模型接入（Spring AI 的 Python 替代）。

两种后端，靠环境变量切换：

    TEACHING_LLM=mock    # 默认。完全离线、结果确定，用于演示流程与跑测试
    TEACHING_LLM=openai  # 任何 OpenAI 兼容接口：OpenAI / DeepSeek / Qwen / vLLM / Ollama

真实模式需要的变量：

    OPENAI_API_KEY=sk-...
    TEACHING_MODEL=gpt-4o-mini        # 或 deepseek-chat / qwen-plus ...
    OPENAI_BASE_URL=https://...       # 可选，本地模型或第三方网关时填
    TEACHING_EMBED_MODEL=bge-m3       # 可选，RAG 向量模型（Ollama）

为什么要有这一层（对应 Spring AI 的 ChatClient/ChatModel）：
业务流程（意图识别、工作流、RAG、评测）不应该绑定某个模型供应商。
把模型调用抽成统一接口，流程就能在离线 mock 下被复现和测试，
切换真实模型时业务代码一行不改。这正是文档 §6「不要让业务流程绑定框架专有 API」的落地。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from typing import Any, Callable, Iterator

DEFAULT_MODEL = "gpt-4o-mini"
EMBED_DIM = 256  # mock 向量维度；真实模型维度由模型决定，索引会记录并校验


# --------------------------------------------------------------------------- 配置
def current_mode() -> str:
    return os.getenv("TEACHING_LLM", "mock").strip().lower()


def model_name() -> str:
    return os.getenv("TEACHING_MODEL", DEFAULT_MODEL)


def embed_model_name() -> str:
    return os.getenv("TEACHING_EMBED_MODEL", "mock-hash-" + str(EMBED_DIM))


def describe() -> str:
    if current_mode() == "mock":
        return "LLM 后端：mock（离线，无需 API key）"
    base = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    return f"LLM 后端：openai（model={model_name()}, base_url={base}）"


# --------------------------------------------------------------------------- 工具
def extract_json(text: str) -> dict[str, Any]:
    """从模型输出里抠出 JSON，兼容 ```json 围栏与前后缀说明。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return {"_parse_error": True, "raw": text}


def _tokenize_zh(text: str) -> list[str]:
    """中文按字符 bigram + 英文/数字按词切分。用于 mock 向量与 BM25。"""
    tokens: list[str] = []
    for run in re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        if re.match(r"[a-zA-Z0-9]+", run):
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
            if len(run) == 1:
                tokens.append(run)
    return tokens


# --------------------------------------------------------------------------- mock 意图抽取
_SUBJECTS = ["数学", "语文", "英语", "物理", "化学", "生物", "科学", "道德与法治"]
_GRADES = ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"]
_DATE_RE = re.compile(r"(\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}|周[一二三四五六日天]|明天|后天)")
_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}


def mock_extract_intent(text: str) -> dict[str, Any]:
    """确定性的意图/槽位抽取替身。

    真实模式下这一步由 LLM 完成（见 m02 的 prompt）；mock 用规则实现，
    目的是让工作流、评测在离线时也有稳定、可断言的输入。
    """
    slots: dict[str, Any] = {}

    if any(k in text for k in ("什么是", "如何", "怎么", "规定", "流程", "吗？")):
        intent = "knowledge_qa"
    elif any(k in text for k in ("创建", "安排", "组织", "帮我")):
        intent = "create_activity"
    elif "？" in text or "?" in text:
        intent = "knowledge_qa"
    else:
        intent = "unknown"

    if "教研" in text:
        slots["activity_type"] = "教研活动"
    elif "培训" in text:
        slots["activity_type"] = "培训"
    elif "公开课" in text:
        slots["activity_type"] = "公开课"

    for s in _SUBJECTS:
        if s in text:
            slots["subject"] = s
            break
    for g in _GRADES:
        if g in text:
            slots["grade"] = g
            break

    # 取「最新」匹配：澄清/修正追加在文本末尾，应覆盖先前的值
    dates = list(_DATE_RE.finditer(text))
    if dates:
        slots["date_text"] = dates[-1].group(1)
    elif "下周" in text or "本周" in text:
        slots["time_hint"] = "下周" if "下周" in text else "本周"

    aud = re.search(r"面向([^，。,]+)", text)
    if aud:
        slots["audience"] = aud.group(1).strip()

    cnt = re.search(r"([一两二三四五1-5])\s*位主讲", text)
    if cnt:
        raw = cnt.group(1)
        slots["speaker_count"] = _CN_NUM.get(raw, int(raw) if raw.isdigit() else 1)

    name_matches = list(re.finditer(r"主讲人[：:]?\s*([^，。,]+)", text))
    if name_matches:
        picked = [n.strip() for n in re.split(r"[、和,]", name_matches[-1].group(1)) if n.strip()]
        # 过滤掉"两位主讲人"这类数量短语误匹配
        picked = [n for n in picked if not re.match(r"^[一两二三四五1-5]位", n) and len(n) >= 2]
        if picked:
            slots["speakers"] = picked

    required = ["activity_type", "subject", "date_text", "audience", "speakers"]
    missing = [f for f in required if f not in slots]
    question_map = {
        "activity_type": "请问是教研活动还是培训？",
        "subject": "请问是哪个学科？",
        "date_text": "请问具体是哪一天、什么时间？",
        "audience": "请问面向哪些教师？",
        "speakers": "请问主讲人是谁？",
    }
    return {
        "intent": intent,
        "slots": slots,
        "missingFields": missing,
        "questions": [question_map[f] for f in missing],
        "confidence": 0.9 if not missing else 0.6,
    }


# --------------------------------------------------------------------------- mock RAG 回答
_EVIDENCE_RE = re.compile(r"【片段\s+([^\s|】]+)[^】]*】\n(.*?)(?=\n【片段|\Z)", re.S)


def mock_rag_answer(user_prompt: str) -> dict[str, Any]:
    """从 prompt 中的证据块构造带引用的回答；无证据则拒答。"""
    evidences = _EVIDENCE_RE.findall(user_prompt)
    if not evidences:
        return {"answer": "无法确认：知识库中没有找到相关依据。", "citations": []}
    parts = []
    citations = []
    for cid, body in evidences:
        first = body.strip().splitlines()[0][:80]
        parts.append(first)
        citations.append(cid)
    return {"answer": "根据知识库：" + "；".join(parts) + "。", "citations": citations}


# --------------------------------------------------------------------------- mock 向量
def mock_embed(texts: list[str]) -> list[list[float]]:
    """hashing-trick 词袋向量：确定性、离线、对共享词汇有相似度。

    这不是语义模型，只用于让混合检索流程可跑通；真实模式用 bge-m3 等。
    """
    out = []
    for text in texts:
        vec = [0.0] * EMBED_DIM
        for tok in _tokenize_zh(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % EMBED_DIM
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


# --------------------------------------------------------------------------- 客户端
class LLM:
    """脚本里直接用：LLM().chat(...) / chat_json(...) / stream(...) / embed(...)。"""

    def __init__(self, mode: str | None = None, model: str | None = None,
                 base_url: str | None = None, embed_model: str | None = None,
                 api_key: str | None = None) -> None:
        self.mode = (mode or current_mode()).lower()
        if self.mode not in {"mock", "openai"}:
            raise ValueError(f"未知 TEACHING_LLM={self.mode!r}，只支持 mock / openai")
        # 实例级覆盖：Web 端可按请求选模型；不传则回退到环境变量
        self.model = model or model_name()
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or None
        self.embed_model = embed_model or embed_model_name()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None
        self.stats = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "errors": 0}

    def label(self) -> str:
        return "mock" if self.mode == "mock" else self.model

    def _openai_client(self):
        if self._client is None:
            from openai import OpenAI

            if not self.api_key:
                raise RuntimeError("openai 模式但未设置 OPENAI_API_KEY；离线请用 mock")
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=float(os.getenv("TEACHING_TIMEOUT", "120")),
                max_retries=int(os.getenv("TEACHING_MAX_RETRIES", "2")),
            )
        return self._client

    # -- 普通对话
    def chat(self, messages: list[dict], temperature: float = 0.0, max_tokens: int | None = None) -> str:
        self.stats["calls"] += 1
        if self.mode == "openai":
            resp = self._openai_client().chat.completions.create(
                model=self.model, temperature=temperature, max_tokens=max_tokens, messages=messages
            )
            usage = getattr(resp, "usage", None)
            if usage:
                self.stats["prompt_tokens"] += usage.prompt_tokens
                self.stats["completion_tokens"] += usage.completion_tokens
            return resp.choices[0].message.content or ""
        # mock：按最后一条 user 消息路由
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        self.stats["prompt_tokens"] += sum(len(m["content"]) for m in messages) // 4
        reply = self._mock_reply(user)
        self.stats["completion_tokens"] += len(reply) // 4
        return reply

    def _mock_reply(self, user: str) -> str:
        if "【片段" in user or "证据" in user:
            return json.dumps(mock_rag_answer(user), ensure_ascii=False)
        if "intent" in user and "slots" in user:
            # m02 的 prompt 里带 JSON  schema 提示；抽取真实需求文本
            m = re.search(r"用户输入[：:]\s*(.+?)(?:\n|$)", user)
            text = m.group(1) if m else user
            return json.dumps(mock_extract_intent(text), ensure_ascii=False)
        if "活动草稿" in user or "activity draft" in user.lower():
            return json.dumps(_mock_draft(user), ensure_ascii=False)
        return "（mock）已收到请求。"

    # -- 结构化输出 + 校验重试（对应 Spring AI Structured Output + Bean Validation）
    def chat_json(
        self,
        messages: list[dict],
        validate: Callable[[dict], str | None],
        retries: int = 2,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        reason = ""
        raw = ""
        for attempt in range(retries + 1):
            msgs = list(messages)
            if attempt:
                msgs.append({"role": "user", "content": f"上一次输出不合格：{reason}。请只输出合法 JSON。"})
            raw = self.chat(msgs, temperature=temperature)
            data = extract_json(raw)
            reason = validate(data) or ""
            if not reason:
                return data
            self.stats["errors"] += 1
        return {"_error": reason, "_raw": raw}

    # -- 流式（对应 Spring AI Streaming / SSE）
    def stream(self, messages: list[dict], temperature: float = 0.0) -> Iterator[str]:
        if self.mode == "openai":
            stream = self._openai_client().chat.completions.create(
                model=self.model, temperature=temperature, messages=messages, stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
            return
        reply = self._mock_reply(next((m["content"] for m in reversed(messages) if m["role"] == "user"), ""))
        for i in range(0, len(reply), 8):
            yield reply[i:i + 8]
            time.sleep(0.01)

    # -- 向量（对应 Spring AI EmbeddingModel）
    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.mode == "openai":
            resp = self._openai_client().embeddings.create(model=self.embed_model, input=texts)
            return [d.embedding for d in resp.data]
        return mock_embed(texts)


def _mock_draft(user: str) -> dict[str, Any]:
    info = mock_extract_intent(user)
    s = info["slots"]
    return {
        "title": f"{s.get('grade', '')}{s.get('subject', '')}{s.get('activity_type', '教学活动')}",
        "activity_type": s.get("activity_type", "教研活动"),
        "subject": s.get("subject", "数学"),
        "date_text": s.get("date_text", "待定"),
        "audience": s.get("audience", "全体教师"),
        "speakers": s.get("speakers", []),
        "duration_minutes": 90,
    }


if __name__ == "__main__":
    print(describe())
    llm = LLM()
    print(llm.chat([{"role": "user", "content": "你好"}]))
