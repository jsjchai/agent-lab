#!/usr/bin/env python3
"""large_api_params · 接口有 40 个参数时，意图识别/槽位怎么做（医教领域）
—— docs/02-prompt-context/02-api-param-strategy.md 代码锚点。

场景：临床教学管理系统「创建教学活动」接口（教学查房/病例讨论/技能培训），共 40 个参数。

问题：靠「抽满 40 个槽位 + 缺啥问啥」必然崩——问 40 个问题体验灾难、模型一次抽 40 字段准确率暴跌、
很多参数根本不该问临床老师（院区、创建人、教学处审批、继续教育学分）。

正确做法：**按来源给参数分层**，Agent 只负责「核心 5 个」，其余由系统注入 / 默认值 / 派生 /
条件规则 / 教学处表单兜底：

    参数分层：system(5) + core(5) + derived(6) + default(10) + conditional(6) + form(8) = 40
    执行流程：意图→核心槽位→组装(注入/派生/默认/条件)→校验→创建 | 草稿+表单兜底

运行（离线）：../../.venv/bin/python large_api_params.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

SYSTEM = 5        # 系统注入：id/院区/创建人/created_at/status
CORE = 5          # 核心必填：type/department/topic/date/instructor
DERIVED = 6       # 派生：title/end_time/duration/week_no/rotation_period/org_id
DEFAULT = 10      # 有默认值：location/mode/... 不问，用默认
CONDITIONAL = 6   # 条件必填：满足条件才需要（如 online→meeting_link、技能培训→mannequin_room）
FORM = 8          # 长尾：交给教学处表单，Agent 不问

TOTAL = SYSTEM + CORE + DERIVED + DEFAULT + CONDITIONAL + FORM   # 40


@dataclass
class Param:
    name: str
    category: str                     # system/core/derived/default/conditional/form
    askable: bool = False             # 是否允许 Agent 向用户提问
    default: object = None
    condition: Callable | None = None # 条件必填的触发条件


CORE_PARAMS = ["session_type", "department", "topic", "date_text", "instructor"]

PARAMS: list[Param] = [
    # --- system(5)：绝不问，来自可信上下文
    Param("id", "system"), Param("tenant_id", "system"), Param("creator_id", "system"),
    Param("created_at", "system"), Param("status", "system"),
    # --- core(5)：Agent 需要抽取/澄清
    Param("session_type", "core", askable=True), Param("department", "core", askable=True),
    Param("topic", "core", askable=True), Param("date_text", "core", askable=True),
    Param("instructor", "core", askable=True),
    # --- derived(6)：计算得出
    Param("title", "derived"), Param("end_time", "derived"), Param("duration_minutes", "derived"),
    Param("week_no", "derived"), Param("rotation_period", "derived"), Param("org_id", "derived"),
    # --- default(10)：有默认值
    Param("location", "default", default="示教室"), Param("mode", "default", default="线下"),
    Param("max_participants", "default", default=20), Param("notify_channel", "default", default="站内信"),
    Param("remind_minutes", "default", default=30), Param("allow_guest", "default", default=False),
    Param("record_enabled", "default", default=True), Param("materials_required", "default", default=True),
    Param("sign_in_required", "default", default=True), Param("auto_approve", "default", default=False),
    # --- conditional(6)：条件必填
    Param("mannequin_room", "conditional", condition=lambda d: d.get("session_type") == "技能培训"),
    Param("meeting_link", "conditional", condition=lambda d: d.get("mode") == "线上"),
    Param("platform", "conditional", condition=lambda d: d.get("mode") == "线上"),
    Param("material_url", "conditional", condition=lambda d: d.get("materials_required") is True),
    Param("supervisor_required", "conditional", condition=lambda d: d.get("audience") == "实习生"),
    Param("video_archive_path", "conditional", condition=lambda d: d.get("record_enabled") is True),
    # --- form(8)：长尾配置，交给教学处表单
    Param("budget_code", "form"), Param("approval_flow", "form"), Param("custom_tags", "form"),
    Param("contact_phone", "form"), Param("internal_note", "form"), Param("cme_credits", "form"),
    Param("archive_policy", "form"), Param("external_ref", "form"),
]
assert len(PARAMS) == TOTAL, f"参数数应为 {TOTAL}，实际 {len(PARAMS)}"


# --------------------------------------------------------------------------- 派生规则
def derive_all(core: dict, ctx: dict) -> dict:
    """从核心槽位 + 上下文派生 6 个字段（不向用户提问）。"""
    duration = 60
    date = core.get("date_text", "")
    department = core.get("department", "")
    topic = core.get("topic", "")
    stype = core.get("session_type", "教学活动")
    return {
        "title": f"{department}{topic}{stype}".strip(),
        "duration_minutes": duration,
        "end_time": f"{date}+{duration}min",        # 简化：真实用 datetime
        "week_no": "W47",                            # 简化：真实按日期算 ISO 周
        "rotation_period": "2026-11 轮转周期",
        "org_id": ctx["org_id"],
    }


# --------------------------------------------------------------------------- 组装 + 校验
@dataclass
class Plan:
    dto: dict = field(default_factory=dict)
    questions: list[str] = field(default_factory=list)
    form_fields: list[str] = field(default_factory=list)
    needs_draft: bool = False
    stats: dict = field(default_factory=dict)


QUESTION_MAP = {
    "session_type": "请问是教学查房、病例讨论、技能培训还是理论授课？",
    "department": "请问是哪个科室？",
    "topic": "请问围绕什么病例或主题？",
    "date_text": "请问安排在哪一天？",
    "instructor": "请问带教老师是谁？",
}


def assemble(slots: dict, ctx: dict, max_questions: int = 3) -> Plan:
    """把 40 个参数分成：已确定 / 要问 / 走表单 / 先草稿。"""
    plan = Plan()
    # 1) 系统字段：从可信上下文注入（不问）
    sys_map = {"id": ctx.get("new_id"), "tenant_id": ctx["tenant_id"], "creator_id": ctx["creator_id"],
               "created_at": ctx["now"], "status": "created"}
    for p in PARAMS:
        if p.category == "system":
            plan.dto[p.name] = sys_map[p.name]
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
    # 5) 条件必填：条件满足且缺失 → 交表单（不追问）
    for p in PARAMS:
        if p.category == "conditional" and p.condition and p.condition(plan.dto) and p.name not in plan.dto:
            plan.form_fields.append(p.name)
    # 6) 长尾字段：一律走表单
    plan.form_fields += [p.name for p in PARAMS if p.category == "form"]
    # 7) 核心缺项：最多问 3 个；超过则先存草稿
    if missing_core:
        plan.needs_draft = len(missing_core) > max_questions
        plan.questions = [QUESTION_MAP[n] for n in missing_core[:max_questions]]
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
    print(f"【large_api_params · 医教】40 参接口怎么处理（共 {TOTAL} 个参数）")
    ctx = {"tenant_id": "hosp-01", "creator_id": "teacher-01", "org_id": "dept-心内科",
           "now": "2026-11-22T10:00", "new_id": "ts-001"}

    cases = [
        ("完整输入", {"session_type": "教学查房", "department": "心内科", "topic": "急性胸痛",
                      "date_text": "11月25日", "instructor": "张三", "audience": "规培生"}),
        ("缺 2 个核心", {"session_type": "病例讨论", "department": "呼吸科", "topic": "社区获得性肺炎"}),
        ("几乎没信息", {"department": "心内科"}),
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

    print("\n  关键结论：40 个参数，Agent 实际只问 ≤3 个核心缺项；院区/创建人注入、派生生标题/时长、")
    print("  默认填充地点/模式、条件与长尾走教学处表单。把「抽满 40 个」变成「只抽核心 + 其余自动补」。")


def selftest() -> None:
    ctx = {"tenant_id": "hosp-01", "creator_id": "teacher-01", "org_id": "dept-心内科",
           "now": "now", "new_id": "ts-001"}
    full = {"session_type": "教学查房", "department": "心内科", "topic": "急性胸痛",
            "date_text": "11月25日", "instructor": "张三", "audience": "规培生"}
    p = assemble(full, ctx)
    assert len(PARAMS) == 40
    assert p.questions == []
    assert not validate(p)
    assert p.dto["title"] == "心内科急性胸痛教学查房"
    assert p.dto["creator_id"] == "teacher-01"          # 系统注入
    assert p.dto["location"] == "示教室"                 # 默认填充
    assert not any("tenant" in q or "creator" in q for q in p.questions)
    q = assemble({"session_type": "病例讨论", "department": "呼吸科", "topic": "社区获得性肺炎"}, ctx)
    assert len(q.questions) == 2 and not q.needs_draft
    q2 = assemble({"department": "心内科"}, ctx)
    assert q2.needs_draft and len(q2.questions) <= 3
    q3 = assemble({**full, "session_type": "技能培训"}, ctx)
    assert "mannequin_room" in q3.form_fields
    assert validate(assemble({"department": "心内科"}, ctx))


if __name__ == "__main__":
    demo()
