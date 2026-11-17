#!/usr/bin/env python3
"""m02 · Prompt/Context Engineering：意图识别 + 槽位抽取 + 缺项澄清 —— 对应文档 §4。

文档 §4 的 Teaching 实战：面对「帮我创建下周的数学教研活动，面向三年级教师，
安排两位主讲人」，系统应识别 intent/slots/missingFields/questions，
判断哪些信息可查、哪些必须澄清，最终生成草稿而非直接创建。

本例演示：
1. 用结构化 prompt 让模型输出 intent/slots/missingFields/questions。
2. 对至少 20 条真实表达做回归测试（mock 下确定性可断言）。
3. Prompt 版本管理：版本号 + 变更记录，变更触发回归。

运行（离线）：
    ../../.venv/bin/python m02_intent_slots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.llm import LLM, describe, extract_json

# Prompt 版本管理（文档 §4）：改 prompt 必须升版本并跑回归。
PROMPT_VERSION = "intent-v2"

SYSTEM_PROMPT = """你是 Teaching 教学活动助手的意图识别模块。只输出一个 JSON 对象，不要解释。

intent 取值：create_activity / knowledge_qa / unknown。

slots 只能使用以下键（不要自创键名）：
- activity_type：教研活动 / 培训 / 公开课
- subject：学科名（数学/语文/英语等）
- grade：一年级/二年级/三年级/四年级/五年级/六年级
- date_text：具体日期，如 "11月20日"/"明天"/"周二"。若用户只说"下周"这类模糊时间，不要填 date_text，改填 time_hint="下周"
- audience：参与对象，如 "三年级教师"
- speaker_count：整数（主讲人数）
- speakers：人名数组，如 ["张三","李四"]。不知道具体人名就不要填 speakers

missingFields：从 [activity_type, subject, date_text, audience, speakers] 中选出仍缺的必填项，必须用这些英文键名。
questions：对应的中文澄清问题数组。
规则：不要编造用户没说的信息。

示例输入：创建11月20日数学教研活动，面向三年级教师，主讲人：张三、李四
示例输出：{"intent":"create_activity","slots":{"activity_type":"教研活动","subject":"数学","grade":"三年级","date_text":"11月20日","audience":"三年级教师","speakers":["张三","李四"]},"missingFields":[],"questions":[]}"""


def build_messages(user_text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"用户输入：{user_text}\n请输出 intent/slots/missingFields/questions。"},
    ]


def _validate_intent(data: dict) -> str | None:
    """校验意图 JSON 结构（真实小模型可能漏字段/类型错）。"""
    if not isinstance(data, dict):
        return "顶层须为 JSON 对象"
    if data.get("intent") not in {"create_activity", "knowledge_qa", "unknown"}:
        return "intent 须为 create_activity/knowledge_qa/unknown"
    if not isinstance(data.get("slots"), dict):
        return "slots 须为对象"
    if not isinstance(data.get("missingFields"), list):
        return "missingFields 须为数组"
    if not isinstance(data.get("questions"), list):
        return "questions 须为数组"
    return None


_REQUIRED = ["activity_type", "subject", "date_text", "audience", "speakers"]
_QUESTION_MAP = {
    "activity_type": "请问是教研活动、培训还是公开课？",
    "subject": "请问是哪个学科？",
    "date_text": "请问具体是哪一天？",
    "audience": "请问面向哪些教师？",
    "speakers": "请问主讲人是谁？",
}
_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}


def _normalize(result: dict, user_text: str) -> dict:
    """确定性归一化：模型负责语义抽取槽位，缺项由代码按必填字段重算。

    小模型常漂移键名/类型（speakers:""、speaker_count:"两位"、missingFields 用中文），
    这里统一清洗，保证下游工作流拿到规范结构。对应文档 §3「未经校验的输出不得进入业务流程」。
    """
    slots = result.get("slots") or {}
    clean: dict = {}
    for k, v in slots.items():
        if v in (None, "", [], {}):
            continue
        if k == "speakers":
            if isinstance(v, str):
                v = [x.strip() for x in v.replace("、", ",").replace("和", ",").split(",") if x.strip()]
            if isinstance(v, list):
                v = [str(x).strip() for x in v if str(x).strip()]
            if not v:
                continue
        if k == "speaker_count":
            if isinstance(v, str):
                v = _CN_NUM.get(v.replace("位", "").strip(), None)
            if not isinstance(v, int):
                continue
        clean[k] = v

    # 日期确定性兜底：取文本中「最后一个具体日期」（澄清/修正追加在末尾，应优先）。
    # 小模型常忽略最新补充而沿用旧值（如把"下周"当日期），这里用规则纠正。
    from common.llm import _DATE_RE

    specific = list(_DATE_RE.finditer(user_text))
    if specific:
        clean["date_text"] = specific[-1].group(1)
        clean.pop("time_hint", None)
    elif "date_text" in clean and not _DATE_RE.fullmatch(str(clean["date_text"])):
        # 模型给了不可解析的模糊日期（下周/本周）=> 视为缺项，触发澄清
        clean.pop("date_text")
        if "下周" in user_text or "本周" in user_text:
            clean["time_hint"] = "下周" if "下周" in user_text else "本周"

    # 缺项由代码确定性计算，不信任模型的 missingFields 命名
    missing = [f for f in _REQUIRED if f not in clean]
    questions = result.get("questions") or []
    if not isinstance(questions, list) or not questions:
        questions = [_QUESTION_MAP[f] for f in missing]
    return {
        "intent": result.get("intent", "unknown"),
        "slots": clean,
        "missingFields": missing,
        "questions": questions,
        "confidence": result.get("confidence", 0.7),
    }


def recognize(llm: LLM, user_text: str) -> dict:
    # 带校验重试的结构化抽取；真实小模型 JSON 不稳时自动重试。
    result = llm.chat_json(build_messages(user_text), validate=_validate_intent, retries=2)
    if "_error" in result:
        # 兜底：解析仍失败时回退到确定性规则抽取，保证工作流不崩（记录告警）
        from common.llm import mock_extract_intent

        print(f"  [warn] 意图解析失败（{result['_error']}），回退规则抽取")
        return mock_extract_intent(user_text)
    return _normalize(result, user_text)


# --------------------------------------------------------------------------- 回归集（≥20 条）
# (输入, 期望intent, 期望包含的slot, 期望缺失字段)
REGRESSION_CASES = [
    ("帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人", "create_activity", {"subject": "数学"}, ["date_text", "speakers"]),
    ("创建11月20日的数学教研活动，面向三年级教师，主讲人：张三、李四", "create_activity", {"date_text": "11月20日", "speakers": ["张三", "李四"]}, []),
    ("组织明天下午的语文培训，面向全体教师，主讲人：王五", "create_activity", {"subject": "语文", "date_text": "明天"}, []),
    ("帮我安排一个教研活动", "create_activity", {}, ["subject", "date_text", "audience", "speakers"]),
    ("创建三年级英语公开课，11月25日，面向三年级教师，主讲人：赵六", "create_activity", {"subject": "英语"}, []),
    ("什么是教研活动？", "knowledge_qa", {}, []),
    ("轮转计划怎么查询？", "knowledge_qa", {}, []),
    ("活动时长有什么规定吗？", "knowledge_qa", {}, []),
    ("创建下周二的数学教研活动，面向四年级教师，主讲人：张三、李四", "create_activity", {"date_text": "周二"}, []),
    ("安排培训，主讲人：陈明", "create_activity", {"activity_type": "培训"}, ["subject", "date_text", "audience"]),
    ("帮我创建数学教研活动，11月20日，面向三年级教师", "create_activity", {"subject": "数学"}, ["speakers"]),
    ("创建教研活动，面向三年级教师，主讲人：张三、李四", "create_activity", {}, ["subject", "date_text"]),
    ("随便聊聊", "unknown", {}, []),
    ("创建五年级科学教研活动，后天，面向五年级教师，主讲人：刘芳", "create_activity", {"grade": "五年级", "date_text": "后天"}, []),
    ("数学教研活动的流程是什么？", "knowledge_qa", {}, []),
    ("帮我组织一个培训", "create_activity", {"activity_type": "培训"}, ["subject", "date_text", "audience", "speakers"]),
    ("创建11月20日数学教研活动，面向三年级教师，安排三位主讲人", "create_activity", {"speaker_count": 3}, ["speakers"]),
    ("如何创建教学活动？", "knowledge_qa", {}, []),
    ("创建六年级语文教研活动，11月28日，面向六年级教师，主讲人：林静、周涛", "create_activity", {"grade": "六年级"}, []),
    ("安排下周的教研活动，面向三年级教师，主讲人：张三", "create_activity", {}, ["subject", "date_text"]),
    ("创建数学教研活动，面向三年级教师，主讲人：张三、李四", "create_activity", {"subject": "数学"}, ["date_text"]),
]


def run_regression(llm: LLM, verbose: bool = False) -> tuple[int, int]:
    passed = 0
    for text, want_intent, want_slots, want_missing in REGRESSION_CASES:
        result = recognize(llm, text)
        ok = result.get("intent") == want_intent
        for k, v in want_slots.items():
            ok = ok and result.get("slots", {}).get(k) == v
        missing = set(result.get("missingFields", []))
        ok = ok and set(want_missing).issubset(missing)
        passed += ok
        if verbose:
            mark = "✓" if ok else "✗"
            print(f"  {mark} {text[:30]}… -> {result.get('intent')} missing={sorted(missing)}")
    return passed, len(REGRESSION_CASES)


def demo() -> None:
    print(f"【m02 意图识别】{describe()}  prompt={PROMPT_VERSION}")
    llm = LLM()
    example = "帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人"
    result = recognize(llm, example)
    print(f"\n  输入：{example}")
    print(f"  intent：{result['intent']}")
    print(f"  slots：{result['slots']}")
    print(f"  缺项：{result['missingFields']}")
    print(f"  澄清问题：{result['questions']}")
    print("\n  回归测试（21 条真实表达）：")
    passed, total = run_regression(llm, verbose=True)
    print(f"\n  通过 {passed}/{total}")


def selftest() -> None:
    llm = LLM("mock")
    passed, total = run_regression(llm)
    assert passed == total, f"回归未全过：{passed}/{total}"


if __name__ == "__main__":
    demo()
