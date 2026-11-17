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
PROMPT_VERSION = "intent-v1"

SYSTEM_PROMPT = """你是 Teaching 教学活动助手的意图识别模块。
只输出 JSON，字段：intent / slots / missingFields / questions / confidence。
intent 取值：create_activity / knowledge_qa / unknown。
slots 可含：activity_type / subject / grade / date_text / time_hint / audience / speaker_count / speakers。
missingFields 列出创建活动还缺的必填字段；questions 给出对应的澄清问题。
不要编造用户没说的信息；不确定就放进 missingFields。"""


def build_messages(user_text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"用户输入：{user_text}\n请输出 intent/slots/missingFields/questions。"},
    ]


def recognize(llm: LLM, user_text: str) -> dict:
    raw = llm.chat(build_messages(user_text))
    return extract_json(raw)


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
