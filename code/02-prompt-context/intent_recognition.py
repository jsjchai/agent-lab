#!/usr/bin/env python3
"""intent_recognition · 意图识别独立 demo —— 对应 docs/02-prompt-context/01-intent-recognition.md。

意图识别是 Agent 的「第一道门」：先判断用户想干什么，再决定走哪条流程、抽哪些槽位、缺什么要澄清。
本 demo 用 4 个意图 + 5 个槽位，演示一条完整的意图识别流水线：

    文本 → 分类器（规则基线 / LLM 结构化）→ 归一化 → 置信度决策 → 执行/澄清/转人工
         → 评测（标注集算准确率）

两个分类器对照，是本 demo 的核心教学点：
- **规则基线**：便宜、确定、可解释，但换个说法就漏（"帮我搞个教研" 不含"创建"就识别不出）。
- **LLM 结构化**：能理解同义表达，但会「漂移」——键名/类型/枚举不规范（mock 里故意模拟），
  必须靠**归一化 + 校验**兜底。这正是 docs/02 与 teaching-agent/m02 的结论。

运行（离线 mock，无需 key）：
    cd code/02-prompt-context && ../../.venv/bin/python intent_recognition.py
接真实模型（Ollama / 任意 OpenAI 兼容）：
    TEACHING_LLM=openai OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \
    TEACHING_MODEL=qwen2.5:7b ../../.venv/bin/python intent_recognition.py
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- 意图与槽位定义
INTENTS = ["create_activity", "query_activity", "knowledge_qa", "chitchat"]
SLOT_KEYS = ["activity_type", "subject", "grade", "date_text", "audience", "speakers"]
REQUIRED_SLOTS = ["activity_type", "subject", "date_text", "audience", "speakers"]

SUBJECTS = ["数学", "语文", "英语", "物理", "化学", "生物", "科学"]
GRADES = ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"]
DATE_RE = re.compile(r"(\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}|周[一二三四五六日天]|明天|后天)")


# --------------------------------------------------------------------------- 规则基线分类器
def rule_based(text: str) -> dict:
    """确定性规则基线：关键词命中。便宜可解释，但脆弱（同义改写会漏）。"""
    intents: list[str] = []
    if any(k in text for k in ("创建", "安排", "组织", "搞个", "弄个")):
        intents.append("create_activity")
    if any(k in text for k in ("查询", "查一下", "有哪些")):
        intents.append("query_activity")
    if any(k in text for k in ("什么是", "如何", "怎么", "规定", "流程")):
        intents.append("knowledge_qa")
    if not intents:
        intents = ["chitchat"]
    slots = extract_slots_by_rule(text)
    # 规则基线置信度：命中关键词越多越高
    confidence = min(0.95, 0.5 + 0.15 * len(intents) + 0.05 * len(slots))
    return {"intents": intents, "slots": slots, "confidence": round(confidence, 2), "raw": None}


def extract_slots_by_rule(text: str) -> dict:
    slots: dict = {}
    if "教研" in text:
        slots["activity_type"] = "教研活动"
    elif "培训" in text:
        slots["activity_type"] = "培训"
    elif "公开课" in text:
        slots["activity_type"] = "公开课"
    for s in SUBJECTS:
        if s in text:
            slots["subject"] = s
            break
    for g in GRADES:
        if g in text:
            slots["grade"] = g
            break
    dates = list(DATE_RE.finditer(text))
    if dates:
        slots["date_text"] = dates[-1].group(1)
    aud = re.search(r"面向([^，。,]+)", text)
    if aud:
        slots["audience"] = aud.group(1).strip()
    names = re.search(r"主讲人[：:]?\s*([^，。,]+)", text)
    if names:
        picked = [n.strip() for n in re.split(r"[、和,]", names.group(1)) if n.strip()]
        picked = [n for n in picked if len(n) >= 2 and not re.match(r"^[一两二三四五1-5]位", n)]
        if picked:
            slots["speakers"] = picked
    return slots


# --------------------------------------------------------------------------- LLM 结构化分类器
SYSTEM_PROMPT = """你是意图识别模块。只输出一个 JSON 对象，字段：intents / slots / confidence。
intents 是数组，取值从 [create_activity, query_activity, knowledge_qa, chitchat] 中选，可多选。
slots 只能用这些键：activity_type / subject / grade / date_text / audience / speakers。
confidence 是 0-1 的小数。不要编造用户没说的信息。"""


def mock_llm_output(text: str) -> str:
    """确定性 LLM 替身：能理解同义表达，但**故意模拟小模型漂移**（键名/类型/枚举不规范），
    用来演示「为什么必须归一化」。真实模型经 TEACHING_LLM=openai 切换。"""
    slots = extract_slots_by_rule(text)
    intents = []
    if any(k in text for k in ("创建", "安排", "组织", "搞个", "弄个", "办一个", "来一场")):
        intents.append("create")                      # 漂移：简写 create
    if any(k in text for k in ("查", "有哪些", "看看")):
        intents.append("query_activity")
    if any(k in text for k in ("什么是", "如何", "怎么", "规定")):
        intents.append("knowledge_qa")
    if not intents:
        intents = ["chitchat"]
    # 漂移：speakers 有时返回字符串，activity_type 有时返回中文枚举外的值
    if "speakers" in slots:
        slots["speakers"] = "、".join(slots["speakers"])   # 漂移：数组→字符串
    return json.dumps({"intents": intents, "slots": slots, "confidence": 0.72}, ensure_ascii=False)


def llm_based(text: str) -> dict:
    """LLM 结构化分类器：真实模式调模型，mock 模式用确定性替身。"""
    if os.getenv("TEACHING_LLM", "mock").lower() == "openai":
        from openai import OpenAI

        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            timeout=120,
        )
        resp = client.chat.completions.create(
            model=os.getenv("TEACHING_MODEL", "gpt-4o-mini"),
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"用户输入：{text}"},
            ],
        )
        raw = resp.choices[0].message.content or ""
    else:
        raw = mock_llm_output(text)
    return normalize(raw)


# --------------------------------------------------------------------------- 归一化（关键兜底）
INTENT_ALIASES = {"create": "create_activity", "query": "query_activity", "qa": "knowledge_qa"}


def normalize(raw: str) -> dict:
    """把小模型/规则的原始输出清洗成规范结构：枚举映射、类型纠正、键名收窄、置信度钳制。

    这是「模型负责语义、代码负责边界」的落地：LLM 能理解同义表达，但格式必须由代码保证。
    """
    data = _extract_json(raw)
    intents = data.get("intents") or []
    if isinstance(intents, str):
        intents = [intents]
    intents = [INTENT_ALIASES.get(str(i).strip(), str(i).strip()) for i in intents]
    intents = [i for i in intents if i in INTENTS] or ["chitchat"]

    slots_in = data.get("slots") or {}
    slots: dict = {}
    for k, v in slots_in.items():
        if k not in SLOT_KEYS or v in (None, "", [], {}):
            continue
        if k == "speakers" and isinstance(v, str):
            v = [x for x in re.split(r"[、和,]", v) if x.strip()]
        if k == "speakers" and isinstance(v, list):
            v = [str(x).strip() for x in v if str(x).strip()]
            if not v:
                continue
        slots[k] = v

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return {"intents": intents, "slots": slots, "confidence": round(max(0.0, min(1.0, confidence)), 2), "raw": raw}


def _extract_json(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    cleaned = fence.group(1).strip() if fence else text.strip()
    for cand in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]):
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    return {}


# --------------------------------------------------------------------------- 置信度决策
def decide(result: dict, threshold: float = 0.6) -> dict:
    """根据意图与槽位决定下一步：执行 / 澄清 / 转人工。"""
    if result["confidence"] < threshold:
        return {"action": "handoff", "reason": f"置信度 {result['confidence']} < 阈值 {threshold}"}
    if "create_activity" in result["intents"]:
        missing = [k for k in REQUIRED_SLOTS if k not in result["slots"]]
        if missing:
            return {"action": "clarify", "reason": "缺必填槽位", "missing": missing,
                    "questions": [QUESTION_MAP[k] for k in missing]}
    return {"action": "execute", "reason": "意图明确且信息完整"}


QUESTION_MAP = {
    "activity_type": "请问是教研活动、培训还是公开课？",
    "subject": "请问是哪个学科？",
    "date_text": "请问具体是哪一天？",
    "audience": "请问面向哪些教师？",
    "speakers": "请问主讲人是谁？",
}


# --------------------------------------------------------------------------- 标注评测集
EVAL_SET = [
    ("创建11月20日的数学教研活动，面向三年级教师，主讲人：张三、李四", ["create_activity"]),
    ("帮我搞个下周的语文教研", ["create_activity"]),
    ("查一下有哪些教研活动", ["query_activity"]),
    ("教研活动怎么申请？", ["knowledge_qa"]),
    ("今天天气不错", ["chitchat"]),
    ("安排一个英语培训，面向全体教师", ["create_activity"]),
    ("查询一下三年级的公开课", ["query_activity"]),
    ("培训有什么规定？", ["knowledge_qa"]),
    ("办一个科学公开课，11月25日", ["create_activity"]),
    ("有哪些轮转计划可以看", ["query_activity"]),
]


def evaluate(classifier) -> dict:
    correct = 0
    for text, gold in EVAL_SET:
        pred = classifier(text)["intents"]
        if set(pred) & set(gold):                 # 命中任一 gold 意图即算对（演示用宽松口径）
            correct += 1
    return {"accuracy": round(correct / len(EVAL_SET), 3), "n": len(EVAL_SET)}


# --------------------------------------------------------------------------- 演示 / 自检
def demo() -> None:
    print("【intent_recognition】意图识别：规则 vs LLM 结构化")
    samples = [
        "帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人",
        "帮我搞个下周的语文教研",                    # 规则能过（含"搞个"），但换个词就漏
        "查一下有哪些教研活动",
        "今天天气不错",
    ]
    for text in samples:
        r = rule_based(text)
        print(f"\n  输入：{text}")
        print(f"    规则 : {r['intents']} conf={r['confidence']} slots={list(r['slots'])}")
        l = llm_based(text)
        print(f"    LLM  : {l['intents']} conf={l['confidence']} slots={list(l['slots'])}（已归一化）")
        d = decide(l)
        print(f"    决策 : {d['action']} — {d['reason']}")

    print("\n  评测（标注集）：")
    print("    规则基线准确率：", evaluate(rule_based))
    print("    LLM 结构化准确率：", evaluate(llm_based))

    print("\n  小模型漂移演示（原始输出 → 归一化）：")
    raw = '{"intents": ["create"], "slots": {"speakers": "张三、李四"}, "confidence": 1.7}'
    print("    原始：", raw)
    print("    归一化：", json.dumps(normalize(raw), ensure_ascii=False))
    print("    → 意图别名映射 / 主讲人字符串转数组 / 置信度钳制到 1.0")


def selftest() -> None:
    # 规则基线：标准表达能识别
    assert "create_activity" in rule_based("创建11月20日的数学教研活动，面向三年级教师")["intents"]
    # LLM 替身的漂移被归一化修复
    r = llm_based("帮我搞个下周的语文教研")
    assert "create_activity" in r["intents"]          # "create" 被映射
    assert r["confidence"] <= 1.0
    # 槽位类型归一化
    n = normalize('{"intents":["create"],"slots":{"speakers":"张三、李四"},"confidence":1.7}')
    assert n["intents"] == ["create_activity"]
    assert n["slots"]["speakers"] == ["张三", "李四"]
    assert n["confidence"] == 1.0
    # 决策：缺槽位 → 澄清；低置信 → 转人工；完整 → 执行
    assert decide({"intents": ["create_activity"], "slots": {}, "confidence": 0.9})["action"] == "clarify"
    assert decide({"intents": ["create_activity"], "slots": {}, "confidence": 0.2})["action"] == "handoff"
    full = {"intents": ["create_activity"], "confidence": 0.9,
            "slots": {k: "x" for k in ["activity_type", "subject", "date_text", "audience", "speakers"]}}
    assert decide(full)["action"] == "execute"
    # 评测：LLM 结构化应不低于规则基线
    assert evaluate(llm_based)["accuracy"] >= evaluate(rule_based)["accuracy"]


if __name__ == "__main__":
    demo()
