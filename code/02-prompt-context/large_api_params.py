#!/usr/bin/env python3
"""large_api_params · 接口有 40 个参数时，意图识别/槽位怎么做 —— docs/02-prompt-context/02-api-param-strategy.md 代码锚点。

问题：若「创建活动」接口有 40 个参数，靠「抽满 40 个槽位 + 缺啥问啥」必然崩：
- 问 40 个问题，用户体验灾难；
- 让模型一次抽 40 个字段，准确率暴跌；
- 很多参数根本不该问用户（系统字段、派生字段、长尾配置）。

正确做法：**按来源给参数分层**，Agent 只负责「核心 5~6 个」，其余由系统注入 / 默认值 / 派生 / 条件规则 /
表单兜底。本 demo 演示这套「40 参」策略：

    参数分层：system(5) + core(5) + derived(6) + default(10) + conditional(6) + form(8) = 40
    执行流程：意图→核心槽位→组装(注入/派生/默认/条件)→校验→创建 | 草稿+表单兜底

运行（离线）：../../.venv/bin/python large_api_params.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# --------------------------------------------------------------------------- 40 个参数的定义
SYSTEM = 5        # 系统注入：id/tenant/creator/created_at/status
CORE = 5          # 核心必填：type/subject/date/audience/speakers
DERIVED = 6       # 派生：title/end_time/duration/week_no/term/org_id
DEFAULT = 10      # 有默认值：location/mode/... 不问，用默认
CONDITIONAL = 6   # 条件必填：满足条件才需要（如 online→meeting_link）
FORM = 8          # 长尾：交给 Web 表单，Agent 不问

TOTAL = SYSTEM + CORE + DERIVED + DEFAULT + CONDITIONAL + FORM   # 40


@dataclass
class Param:
    name: str
    category: str                     # system/core/derived/default/conditional/form
    askable: bool = False             # 是否允许 Agent 向用户提问
    default: object = None
    derive: Callable | None = None    # 派生函数
    condition: Callable | None = None # 条件必填的触发条件


# 核心必填（Agent 只问这 5 个里缺的）
CORE_PARAMS = ["activity_type", "subject", "date_text", "audience", "speakers"]

# 参数表（40 个；name 覆盖全部）
PARAMS: list[Param] = [
    # --- system(5)：绝不问，来自可信上下文
    Param("id", "system"), Param("tenant_id", "system"), Param("creator_id", "system"),
    Param("created_at", "system"), Param("status", "system"),
    # --- core(5)：Agent 需要抽取/澄清
    Param("activity_type", "core", askable=True), Param("subject", "core", askable=True),
    Param("date_text", "core", askable=True), Param("audience", "core", askable=True),
    Param("speakers", "core", askable=True),
    # --- derived(6)：计算得出
    Param("title", "derived"), Param("end_time", "derived"), Param("duration_minutes", "derived"),
    Param("week_no", "derived"), Param("term", "derived"), Param("org_id", "derived"),
    # --- default(10)：有默认值
    Param("location", "default", default="线上会议室"), Param("mode", "default", default="online"),
    Param("max_participants", "default", default=50), Param("notify_channel", "default", default="站内信"),
    Param("remind_minutes", "default", default=15), Param("allow_guest", "default", default=False),
    Param("record_enabled", "default", default=True), Param("materials_required", "default", default=False),
    Param("sign_in_required", "default", default=True), Param("auto_approve", "default", default=True),
    # --- conditional(6)：条件必填
    Param("trainer_qualification", "conditional", condition=lambda d: d.get("activity_type") == "培训"),
    Param("meeting_link", "conditional", condition=lambda d: d.get("mode") == "online"),
    Param("platform", "conditional", condition=lambda d: d.get("mode") == "online"),
    Param("material_url", "conditional", condition=lambda d: d.get("materials_required") is True),
    Param("sign_in_code", "conditional", condition=lambda d: d.get("sign_in_required") is True),
    Param("guest_limit", "conditional", condition=lambda d: d.get("allow_guest") is True),
    # --- form(8)：长尾配置，交给 Web 表单
    Param("budget_code", "form"), Param("approval_flow", "form"), Param("custom_tags", "form"),
    Param("contact_phone", "form"), Param("internal_note", "form"), Param("kpi_weight", "form"),
    Param("archive_policy", "form"), Param("external_ref", "form"),
]
assert len(PARAMS) == TOTAL, f"参数数应为 {TOTAL}，实际 {len(PARAMS)}"


# --------------------------------------------------------------------------- 派生规则
def derive_all(core: dict, ctx: dict) -> dict:
    """从核心槽位 + 上下文派生 6 个字段（不向用户提问）。"""
    duration = 90
    date = core.get("date_text", "")
    grade = core.get("grade", "")
    subject = core.get("subject", "")
    atype = core.get("activity_type", "教学活动")
    return {
        "title": f"{grade}{subject}{atype}".strip(),
        "duration_minutes": duration,
        "end_time": f"{date}+{duration}min",           # 简化：真实用 datetime
        "week_no": "W47",                              # 简化：真实按日期算 ISO 周
        "term": "2026-秋季学期",
        "org_id": ctx["org_id"],
    }


# --------------------------------------------------------------------------- 组装 + 校验
@dataclass
class Plan:
    dto: dict = field(default_factory=dict)          # 已确定的参数
    questions: list[str] = field(default_factory=list)  # 要问用户的核心缺项（≤3）
    form_fields: list[str] = field(default_factory=list)  # 交给表单的字段
    needs_draft: bool = False                        # 核心不齐 → 先存草稿
    stats: dict = field(default_factory=dict)


QUESTION_MAP = {
    "activity_type": "请问是教研活动、培训还是公开课？",
    "subject": "请问是哪个学科？",
    "date_text": "请问具体是哪一天？",
    "audience": "请问面向哪些教师？",
    "speakers": "请问主讲人是谁？",
}


def assemble(slots: dict, ctx: dict, max_questions: int = 3) -> Plan:
    """把 40 个参数分成：已确定 / 要问 / 走表单 / 先草稿。"""
    plan = Plan()
    # 1) 系统字段：从可信上下文注入（不问）
    for p in PARAMS:
        if p.category == "system":
            plan.dto[p.name] = {"id": ctx.get("new_id"), "tenant_id": ctx["tenant_id"],
                                "creator_id": ctx["creator_id"], "created_at": ctx["now"],
                                "status": "draft" if False else "created"}.get(p.name)
    # 2) 核心字段：从槽位取，缺的记录
    missing_core = []
    for name in CORE_PARAMS:
        if slots.get(name):
            plan.dto[name] = slots[name]
        else:
            missing_core.append(name)
    # 3) 派生字段
    plan.dto.update(derive_all(slots, ctx))
    # 4) 默认字段
    for p in PARAMS:
        if p.category == "default":
            plan.dto[p.name] = p.default
    # 5) 条件必填：条件满足且缺失 → 交表单（不追问，交给表单/系统补）
    for p in PARAMS:
        if p.category == "conditional" and p.condition and p.condition(plan.dto) and p.name not in plan.dto:
            plan.form_fields.append(p.name)
    # 6) 长尾字段：一律走表单
    plan.form_fields += [p.name for p in PARAMS if p.category == "form"]
    # 7) 核心缺项：最多问 3 个；超过则先存草稿
    if missing_core:
        if len(missing_core) > max_questions:
            plan.needs_draft = True
            plan.questions = [QUESTION_MAP[n] for n in missing_core[:max_questions]]
        else:
            plan.questions = [QUESTION_MAP[n] for n in missing_core]
    plan.stats = {
        "total_params": TOTAL,
        "system_injected": SYSTEM,
        "core_resolved": CORE - len(missing_core),
        "derived": DERIVED,
        "defaulted": DEFAULT,
        "conditional_to_form": sum(1 for p in PARAMS if p.category == "conditional" and p.name in plan.form_fields),
        "form_only": FORM,
        "questions": len(plan.questions),
    }
    return plan


def validate(plan: Plan) -> list[str]:
    """调用前校验：核心必填必须齐（系统/派生/默认/条件/表单不在此列）。"""
    return [f"缺少核心参数：{n}" for n in CORE_PARAMS if n not in plan.dto]


# --------------------------------------------------------------------------- 演示 / 自检
def demo() -> None:
    print(f"【large_api_params】40 参接口怎么处理（共 {TOTAL} 个参数）")
    ctx = {"tenant_id": "t1", "creator_id": "u1", "org_id": "o1", "now": "2026-11-17T10:00", "new_id": "act-001"}

    cases = [
        ("完整输入", {"activity_type": "教研活动", "subject": "数学", "date_text": "11月20日",
                      "audience": "三年级教师", "speakers": ["张三", "李四"], "grade": "三年级"}),
        ("缺 2 个核心", {"activity_type": "教研活动", "subject": "数学", "date_text": "11月20日"}),
        ("几乎没信息", {"subject": "数学"}),
    ]
    for title, slots in cases:
        plan = assemble(slots, ctx)
        print(f"\n  ── {title} ──")
        print(f"    参数统计：{plan.stats}")
        print(f"    要问用户：{len(plan.questions)} 个 → {plan.questions}")
        print(f"    走表单：{len(plan.form_fields)} 个（条件+长尾）")
        print(f"    草稿模式：{plan.needs_draft} | 校验错误：{validate(plan) or '无'}")
        if not plan.questions:
            print(f"    可直接创建：title={plan.dto['title']} end={plan.dto['end_time']} status={plan.dto['status']}")

    print("\n  关键结论：40 个参数，Agent 实际只问 ≤3 个核心缺项；系统字段注入、派生字段计算、")
    print("  默认字段填充、条件/长尾走表单。把「抽满 40 个」变成「只抽核心 + 其余自动补」。")


def selftest() -> None:
    ctx = {"tenant_id": "t1", "creator_id": "u1", "org_id": "o1", "now": "now", "new_id": "act-001"}
    full = {"activity_type": "教研活动", "subject": "数学", "date_text": "11月20日",
            "audience": "三年级教师", "speakers": ["张三"], "grade": "三年级"}
    p = assemble(full, ctx)
    assert len(PARAMS) == 40
    assert p.questions == []                          # 完整输入不问
    assert not validate(p)                            # 核心齐，校验通过
    assert p.dto["title"] == "三年级数学教研活动"       # 派生正确
    assert p.dto["creator_id"] == "u1"                # 系统注入
    assert p.dto["location"] == "线上会议室"           # 默认填充
    # 系统字段从不提问
    assert not any("tenant" in q or "creator" in q for q in p.questions)
    # 缺 2 个核心 → 只问 2 个
    q = assemble({"activity_type": "教研活动", "subject": "数学", "date_text": "11月20日"}, ctx)
    assert len(q.questions) == 2 and not q.needs_draft
    # 缺 4 个核心 → 草稿模式，仍只问最多 3 个
    q2 = assemble({"subject": "数学"}, ctx)
    assert q2.needs_draft and len(q2.questions) <= 3
    # 条件字段：培训 → trainer_qualification 进表单
    q3 = assemble({**full, "activity_type": "培训"}, ctx)
    assert "trainer_qualification" in q3.form_fields
    # 校验：核心缺则报错
    assert validate(assemble({"subject": "数学"}, ctx))


if __name__ == "__main__":
    demo()
