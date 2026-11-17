#!/usr/bin/env python3
"""m01 · LLM 基础：结构化输出 + DTO 校验 —— 对应文档 §3。

Spring AI 的「Structured Output + Bean Validation」在 Python 里就是
「LLM 输出 JSON + pydantic 模型校验」。本例演示文档 §3 的验收标准：

    输出可稳定解析；字段缺失、类型错误、非法枚举能被程序拦截，
    未经校验的模型输出不能进入业务流程。

运行（离线）：
    ../../.venv/bin/python m01_structured_output.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import BaseModel, Field, ValidationError, field_validator

from common.llm import LLM, describe


# --------------------------------------------------------------------------- DTO
class ActivityDraft(BaseModel):
    """活动草稿 DTO。对应 Java 的 @NotNull / @Size / 枚举校验。"""

    title: str = Field(min_length=1, max_length=100)
    activity_type: Literal["教研活动", "培训", "公开课"]
    subject: str = Field(min_length=1)
    grade: Literal["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"] | None = None
    date_text: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    speakers: list[str] = Field(min_length=1, max_length=3)
    duration_minutes: int = Field(ge=30, le=240)

    @field_validator("speakers")
    @classmethod
    def speakers_non_empty(cls, v: list[str]) -> list[str]:
        if any(not s.strip() for s in v):
            raise ValueError("主讲人姓名不能为空")
        return v


def validate_payload(data: dict) -> str | None:
    """供 LLM.chat_json 使用的校验器：返回 None=通过，否则返回错误描述。"""
    try:
        ActivityDraft.model_validate(data)
        return None
    except ValidationError as exc:
        return "；".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())


# --------------------------------------------------------------------------- 演示
def demo() -> None:
    print(f"【m01 结构化输出】{describe()}")
    llm = LLM()

    # 1. 让模型输出活动草稿 JSON，并用 pydantic 校验
    messages = [
        {"role": "system", "content": "你是教学活动助手。只输出 JSON 活动草稿，字段：title/activity_type/subject/grade/date_text/audience/speakers/duration_minutes。"},
        {"role": "user", "content": "请为三年级数学教研活动生成一份活动草稿，11月20日，面向三年级教师，主讲人张三、李四，时长90分钟。"},
    ]
    data = llm.chat_json(messages, validate=validate_payload, retries=2)
    if "_error" in data:
        print("  ✗ 模型输出未通过校验：", data["_error"])
        return
    draft = ActivityDraft.model_validate(data)
    print("  ✓ 模型输出通过 DTO 校验：", draft.title)

    # 2. 故意构造非法输出，证明校验能拦截（文档验收核心）
    bad_cases = {
        "字段缺失": {"title": "x", "activity_type": "教研活动"},
        "类型错误": {**draft.model_dump(), "duration_minutes": "九十分钟"},
        "非法枚举": {**draft.model_dump(), "activity_type": "聚餐"},
        "越界数值": {**draft.model_dump(), "duration_minutes": 999},
        "空主讲人": {**draft.model_dump(), "speakers": [""]},
    }
    print("\n  非法输出拦截测试：")
    for name, payload in bad_cases.items():
        err = validate_payload(payload)
        assert err is not None, f"{name} 应当被拦截"
        print(f"    ✓ {name} 被拦截 -> {err[:50]}")

    print(f"\n  调用统计：{llm.stats}")


def selftest() -> None:
    llm = LLM("mock")
    messages = [
        {"role": "system", "content": "输出 JSON 活动草稿"},
        {"role": "user", "content": "请为三年级数学教研活动生成一份活动草稿，11月20日，面向三年级教师，主讲人张三、李四，时长90分钟。"},
    ]
    data = llm.chat_json(messages, validate=validate_payload)
    assert "_error" not in data, data
    ActivityDraft.model_validate(data)
    assert validate_payload({"title": "x"}) is not None
    assert validate_payload({**data, "activity_type": "聚餐"}) is not None


if __name__ == "__main__":
    demo()
