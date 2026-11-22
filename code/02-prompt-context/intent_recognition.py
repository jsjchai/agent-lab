#!/usr/bin/env python3
"""intent_recognition · 意图识别独立 demo（医教领域）—— 对应 docs/02-prompt-context/01-intent-recognition.md。

场景：临床教学管理助手（住院医师规范化培训 / 教学查房 / 病例讨论 / 技能培训）。
意图识别是 Agent 的「第一道门」：先判断用户想干什么，再决定走哪条流程、抽哪些槽位、缺什么要澄清。

四个意图（医教）：
    create_session（创建教学活动：教学查房/病例讨论/技能培训）
    query_session（查询教学活动/排期）
    knowledge_qa（问医教知识：培训规定/查房流程/带教要求）
    chitchat（闲聊）

核心槽位：session_type（活动类型）、department（科室）、topic（病例/主题）、date_text（日期）、instructor（带教老师）。

两个分类器对照（本 demo 核心教学点）：
- **规则基线**：便宜、确定、可解释，但换个说法就漏（"搞个查房" 不含"创建"就识别不出）。
- **LLM 结构化**：能理解同义表达，但会漂移（键名/类型/枚举不规范，mock 里故意模拟），
  必须靠**归一化 + 校验**兜底。

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

# --------------------------------------------------------------------------- 意图与槽位定义
INTENTS = ["create_session", "query_session", "knowledge_qa", "chitchat"]
SLOT_KEYS = ["session_type", "department", "topic", "date_text", "audience", "instructor"]
REQUIRED_SLOTS = ["session_type", "department", "topic", "date_text", "instructor"]

SESSION_TYPES = ["教学查房", "病例讨论", "技能培训", "理论授课"]
DEPARTMENTS = ["心内科", "呼吸科", "消化科", "急诊科", "神经内科", "普外科", "儿科"]
TOPICS = ["急性胸痛", "社区获得性肺炎", "急性腹痛", "糖尿病", "脑卒中", "心肺复苏", "胸腔穿刺"]
AUDIENCES = ["规培生", "住院医师", "实习生", "进修医生", "R1", "R2", "R3"]
DATE_RE = re.compile(r"(\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}|周[一二三四五六日天]|明天|后天|下周三?)")


# --------------------------------------------------------------------------- 规则基线分类器
def rule_based(text: str) -> dict:
    """确定性规则基线：关键词命中。便宜可解释，但脆弱（同义改写会漏）。"""
    intents: list[str] = []
    if any(k in text for k in ("创建", "安排", "组织", "举办", "搞个", "弄个")):
        intents.append("create_session")
    if any(k in text for k in ("查询", "查一下", "有哪些", "排期")):
        intents.append("query_session")
    if any(k in text for k in ("什么是", "如何", "怎么", "规定", "流程", "要求")):
        intents.append("knowledge_qa")
    if not intents:
        intents = ["chitchat"]
    slots = extract_slots_by_rule(text)
    confidence = min(0.95, 0.5 + 0.15 * len(intents) + 0.05 * len(slots))
    return {"intents": intents, "slots": slots, "confidence": round(confidence, 2), "raw": None}


def extract_slots_by_rule(text: str) -> dict:
    slots: dict = {}
    for st in SESSION_TYPES:
        if st in text:
            slots["session_type"] = st
            break
    for d in DEPARTMENTS:
        if d in text:
            slots["department"] = d
            break
    for t in TOPICS:
        if t in text:
            slots["topic"] = t
            break
    for a in AUDIENCES:
        if a in text:
            slots["audience"] = a
            break
    dates = list(DATE_RE.finditer(text))
    if dates:
        slots["date_text"] = dates[-1].group(1)
    names = re.search(r"(?:带教老师|主讲人|授课人)[：:]?\s*([^，。,]+)", text)
    if names:
        picked = [n.strip() for n in re.split(r"[、和,]", names.group(1)) if n.strip()]
        picked = [n for n in picked if len(n) >= 2 and not re.match(r"^[一两二三四五1-5]位", n)]
        if picked:
            slots["instructor"] = picked[0]
    return slots


# --------------------------------------------------------------------------- LLM 结构化分类器
SYSTEM_PROMPT = """你是临床教学管理助手的意图识别模块。只输出一个 JSON 对象，字段：intents / slots / confidence。
intents 是数组，取值从 [create_session, query_session, knowledge_qa, chitchat] 中选，可多选。
slots 只能用这些键：session_type / department / topic / date_text / audience / instructor。
session_type 取值：教学查房 / 病例讨论 / 技能培训 / 理论授课。
confidence 是 0-1 的小数。不要编造用户没说的信息。"""


def mock_llm_output(text: str) -> str:
    """确定性 LLM 替身：能理解同义表达，但**故意模拟小模型漂移**（键名/类型/枚举不规范），
    用来演示「为什么必须归一化」。真实模型经 TEACHING_LLM=openai 切换。"""
    slots = extract_slots_by_rule(text)
    intents = []
    if any(k in text for k in ("创建", "安排", "组织", "举办", "搞个", "弄个", "来一场")):
        intents.append("create")                      # 漂移：简写 create
    if any(k in text for k in ("查", "有哪些", "排期", "看看")):
        intents.append("query_session")
    if any(k in text for k in ("什么是", "如何", "怎么", "规定", "要求")):
        intents.append("knowledge_qa")
    if not intents:
        intents = ["chitchat"]
    return json.dumps({"intents": intents, "slots": slots, "confidence": 0.72}, ensure_ascii=False)


def llm_based(text: str) -> dict:
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
INTENT_ALIASES = {"create": "create_session", "query": "query_session", "qa": "knowledge_qa"}


def normalize(raw: str) -> dict:
    """把小模型/规则的原始输出清洗成规范结构：枚举映射、类型纠正、键名收窄、置信度钳制。"""
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
        if k == "instructor" and isinstance(v, list):
            v = v[0] if v else ""
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
QUESTION_MAP = {
    "session_type": "请问是教学查房、病例讨论、技能培训还是理论授课？",
    "department": "请问是哪个科室？",
    "topic": "请问围绕什么病例或主题？",
    "date_text": "请问安排在哪一天？",
    "instructor": "请问带教老师是谁？",
}


def decide(result: dict, threshold: float = 0.6) -> dict:
    """根据意图与槽位决定下一步：执行 / 澄清 / 转人工。"""
    if result["confidence"] < threshold:
        return {"action": "handoff", "reason": f"置信度 {result['confidence']} < 阈值 {threshold}"}
    if "create_session" in result["intents"]:
        missing = [k for k in REQUIRED_SLOTS if k not in result["slots"]]
        if missing:
            return {"action": "clarify", "reason": "缺必填槽位", "missing": missing,
                    "questions": [QUESTION_MAP[k] for k in missing]}
    return {"action": "execute", "reason": "意图明确且信息完整"}


# --------------------------------------------------------------------------- 路由：调接口 vs 问答
ROUTE_MAP = {
    "create_session": "api_write",
    "query_session": "api_read",
    "knowledge_qa": "knowledge",
    "chitchat": "chat",
}
ROUTE_LABEL = {
    "api_write": "调用业务接口（写：排课/建教学活动，需鉴权与确认）",
    "api_read": "调用业务接口（读：查询教学排期/活动列表）",
    "knowledge": "知识库问答（RAG：培训规定/流程/要求，不改状态）",
    "chat": "闲聊 / 兜底",
}

METHOD_WORDS = ("如何", "怎么", "怎样", "为什么", "是什么", "什么是", "规定", "流程", "要求", "区别", "吗？", "？")
IMPERATIVE_WORDS = ("帮我", "给我", "替我", "安排", "创建", "组织", "举办", "排课", "删除", "修改", "发布", "搞个", "弄个")
SELF_DATA_WORDS = ("我的", "我有哪些", "查一下", "查询", "看看有哪些", "列表", "排期", "记录", "这个系统", "平台")
WRITE_WORDS = ("创建", "安排", "组织", "举办", "排课", "删除", "修改", "发布", "搞个", "弄个")
QUERY_MARKERS = ("查一下", "查询", "看看", "有哪些", "排期", "列表", "记录")


def _hit(text: str, words) -> list[str]:
    return [w for w in words if w in text]


def route(text: str, result: dict) -> dict:
    """判断这次请求走「调接口」还是「问答」，并给出可解释的理由与信号。

    判据优先级（顺序很重要）：
    1. 方法/解释问句（如何/怎么/为什么/规定/流程）+ 非「帮我/给我」祈使 → 问答。
    2. 强查询标记（查一下/查询/看看/排期/列表）→ 读接口。
       这一条要早于「写动作」，否则「查一下我下周的教学安排」含「安排」会被误判成写。
    3. 写动作（安排/创建/排课…）→ 写接口。
    4. 数据指代或查询意图 → 读接口。
    5. 知识意图 → 问答。
    6. 其余 → 闲聊。
    """
    method = _hit(text, METHOD_WORDS)
    self_data = _hit(text, SELF_DATA_WORDS)
    write = _hit(text, WRITE_WORDS)
    query = _hit(text, QUERY_MARKERS)
    intents = result.get("intents", [])

    # 1. 方法问句：问「怎么做」，不是让系统做（即使含"安排/创建"等动作词）
    if method and not any(w in text for w in ("帮我", "给我", "替我")):
        return {"route": "knowledge", "reason": "方法/解释类问句（如何/怎么/规定/流程/要求），走知识问答",
                "signals": {"method": method}}
    # 2. 强查询标记：查询动作优先于写动作词（"查一下…教学安排" 是查，不是排课）
    if query:
        return {"route": "api_read", "reason": "含查询标记（查一下/看看/排期/列表），走业务读接口",
                "signals": {"query": query, "intent": intents}}
    # 3. 写动作 → 写接口
    if write or "create_session" in intents:
        return {"route": "api_write", "reason": "含写动作（安排/创建/排课），走业务写接口",
                "signals": {"write": write, "intent": intents}}
    # 4. 数据指代 / 查询意图 → 读接口
    if self_data or "query_session" in intents:
        return {"route": "api_read", "reason": "查询教学排期/活动列表，走业务读接口",
                "signals": {"self_data": self_data, "intent": intents}}
    # 5. 知识意图
    if "knowledge_qa" in intents or method:
        return {"route": "knowledge", "reason": "培训规定/流程/要求问答，走 RAG",
                "signals": {"method": method, "intent": intents}}
    # 6. 兜底
    return {"route": "chat", "reason": "无明确业务或知识意图，走闲聊/兜底",
            "signals": {"intent": intents}}


# --------------------------------------------------------------------------- 标注评测集
EVAL_SET = [
    ("安排下周三的急性胸痛教学查房，心内科，带教老师张三", ["create_session"]),
    ("帮我搞个社区获得性肺炎的病例讨论", ["create_session"]),
    ("查一下我下周的教学安排", ["query_session"]),
    ("住院医师规范化培训的教学查房有什么要求？", ["knowledge_qa"]),
    ("今天天气不错", ["chitchat"]),
    ("组织一次心肺复苏技能培训，急诊科，带教老师李四", ["create_session"]),
    ("我们科室这周有哪些技能培训", ["query_session"]),
    ("教学查房怎么申请？", ["knowledge_qa"]),
    ("举办一次糖尿病病例讨论，内分泌科", ["create_session"]),
    ("看看下周有哪些排期", ["query_session"]),
]

ROUTE_EVAL = [
    ("安排下周三的急性胸痛教学查房，心内科，带教老师张三", "api_write"),
    ("帮我搞个社区获得性肺炎的病例讨论", "api_write"),
    ("组织一次心肺复苏技能培训，急诊科", "api_write"),
    ("如何安排教学查房？", "knowledge"),          # 陷阱：含"安排"但问方法
    ("教学查房怎么申请？", "knowledge"),          # 陷阱：怎么+申请
    ("住院医师培训有什么要求？", "knowledge"),
    ("查一下我下周的教学安排", "api_read"),
    ("看看下周有哪些排期", "api_read"),
    ("我的教学活动列表", "api_read"),
    ("今天天气不错", "chat"),
]


def evaluate(classifier) -> dict:
    correct = 0
    for text, gold in EVAL_SET:
        pred = classifier(text)["intents"]
        if set(pred) & set(gold):
            correct += 1
    return {"accuracy": round(correct / len(EVAL_SET), 3), "n": len(EVAL_SET)}


def evaluate_route(classifier) -> dict:
    correct = 0
    for text, gold in ROUTE_EVAL:
        if route(text, classifier(text))["route"] == gold:
            correct += 1
    return {"accuracy": round(correct / len(ROUTE_EVAL), 3), "n": len(ROUTE_EVAL)}


# --------------------------------------------------------------------------- 演示 / 自检
def demo() -> None:
    print("【intent_recognition · 医教】意图识别：规则 vs LLM 结构化")
    samples = [
        "安排下周三的急性胸痛教学查房，心内科，带教老师张三",
        "帮我搞个社区获得性肺炎的病例讨论",           # "搞个" 规则能过，换词就漏
        "查一下我下周的教学安排",
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

    print("\n  ── 调接口 vs 问答：怎么判断 ──")
    traps = [
        "如何安排教学查房？",            # 含"安排"但问方法 → 问答
        "教学查房怎么申请？",            # 怎么+申请 → 问答
        "安排下周三的急性胸痛教学查房",   # 祈使+写动作 → 写接口
        "查一下我的教学排期",            # 数据指代 → 读接口
    ]
    for text in traps:
        l = llm_based(text)
        rt = route(text, l)
        print(f"    「{text}」")
        print(f"      意图={l['intents']} → 通道={rt['route']}（{ROUTE_LABEL[rt['route']]}）")
        print(f"      理由：{rt['reason']}")

    print("\n  评测（标注集）：")
    print("    意图识别——规则：", evaluate(rule_based), " LLM：", evaluate(llm_based))
    print("    路由判定——LLM：", evaluate_route(llm_based))


def selftest() -> None:
    assert "create_session" in rule_based("安排下周三的急性胸痛教学查房，心内科")["intents"]
    r = llm_based("帮我搞个社区获得性肺炎的病例讨论")
    assert "create_session" in r["intents"]
    assert r["confidence"] <= 1.0
    n = normalize('{"intents":["create"],"slots":{"instructor":["张三"]},"confidence":1.7}')
    assert n["intents"] == ["create_session"]
    assert n["slots"]["instructor"] == "张三"
    assert n["confidence"] == 1.0
    assert decide({"intents": ["create_session"], "slots": {}, "confidence": 0.9})["action"] == "clarify"
    assert decide({"intents": ["create_session"], "slots": {}, "confidence": 0.2})["action"] == "handoff"
    full = {"intents": ["create_session"], "confidence": 0.9,
            "slots": {k: "x" for k in REQUIRED_SLOTS}}
    assert decide(full)["action"] == "execute"
    assert evaluate(llm_based)["accuracy"] >= evaluate(rule_based)["accuracy"]
    assert route("如何安排教学查房？", llm_based("如何安排教学查房？"))["route"] == "knowledge"   # 陷阱
    assert route("安排下周三的教学查房", llm_based("安排下周三的教学查房"))["route"] == "api_write"
    assert route("查一下我的教学排期", llm_based("查一下我的教学排期"))["route"] == "api_read"
    assert route("今天天气不错", llm_based("今天天气不错"))["route"] == "chat"
    assert evaluate_route(llm_based)["accuracy"] == 1.0


if __name__ == "__main__":
    demo()
