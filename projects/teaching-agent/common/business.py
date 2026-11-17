"""模拟 Teaching 既有业务服务 —— 对应文档 §6/§7/§11「最终写操作由原业务服务执行」。

Agent 只负责理解、查询、校验、构建草稿；**不直接写业务表**。
真正的创建由这里的 create_activity_api() 完成，它继续负责权限、规则、事务和幂等。
生产环境中这就是 Teaching 的既有 REST API，Agent 通过 HTTP 调用它。
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

from .security import AuthError, SecurityContext

# --------------------------------------------------------------------------- 业务数据
ACTIVITY_RULES = {
    "allowed_types": ["教研活动", "培训", "公开课"],
    "min_duration_minutes": 30,
    "max_duration_minutes": 240,
    "min_speakers": 1,
    "max_speakers": 3,
    "grades": ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"],
    "min_advance_days": 1,  # 至少提前 1 天
}

ROTATION_SNAPSHOT = {
    "o1": {"week": "2026-W47", "plan": "三年级数学组本周轮值：集体备课 + 听评课"},
    "o2": {"week": "2026-W47", "plan": "语文组本周轮值：阅读教学研讨"},
    "o3": {"week": "2026-W47", "plan": "英语组本周轮值：口语活动设计"},
}

PARTICIPANTS = {
    "o1": ["张三", "李四", "陈明", "刘芳"],
    "o2": ["王五", "赵六", "林静", "周涛"],
    "o3": ["孙七", "吴八"],
}

# 业务表（模拟 ta_activity）。只有 create_activity_api 能写。
_ACTIVITIES: dict[str, dict] = {}
# 幂等键 -> activity_id，防止重复创建
_IDEMPOTENCY: dict[str, str] = {}


class BusinessRuleError(Exception):
    """业务规则校验失败。"""


def _parse_date(text: str) -> date | None:
    """把 date_text 解析成具体日期。支持 X月X日 / YYYY-MM-DD / 周X / 明天/后天。"""
    today = date(2026, 11, 17)  # 固定"今天"，保证演示与测试可复现
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        return date(today.year, int(m[1]), int(m[2]))
    if text == "明天":
        return today + timedelta(days=1)
    if text == "后天":
        return today + timedelta(days=2)
    m = re.match(r"周([一二三四五六日天])", text)
    if m:
        target = "一二三四五六日".index(m[1]) if m[1] != "天" else 6
        delta = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=delta)
    return None


def validate_draft(ctx: SecurityContext, draft: dict) -> list[str]:
    """业务规则校验（确定性断言，不依赖模型）。返回错误列表，空=通过。"""
    errors: list[str] = []
    rules = ACTIVITY_RULES

    if draft.get("activity_type") not in rules["allowed_types"]:
        errors.append(f"活动类型非法：{draft.get('activity_type')}")
    if draft.get("subject") is None:
        errors.append("缺少学科")
    if draft.get("grade") and draft["grade"] not in rules["grades"]:
        errors.append(f"年级非法：{draft['grade']}")

    dur = draft.get("duration_minutes", 0)
    if not (rules["min_duration_minutes"] <= dur <= rules["max_duration_minutes"]):
        errors.append(f"时长须在 {rules['min_duration_minutes']}~{rules['max_duration_minutes']} 分钟")

    speakers = draft.get("speakers", [])
    if not (rules["min_speakers"] <= len(speakers) <= rules["max_speakers"]):
        errors.append(f"主讲人数量须在 {rules['min_speakers']}~{rules['max_speakers']}")

    d = _parse_date(draft.get("date_text", ""))
    if d is None:
        errors.append(f"无法解析日期：{draft.get('date_text')}")
    elif (d - date(2026, 11, 17)).days < rules["min_advance_days"]:
        errors.append("活动日期须至少提前 1 天")

    # 主讲人必须在当前用户可访问组织内
    accessible = {p for org in ctx.org_ids for p in PARTICIPANTS.get(org, [])}
    for s in speakers:
        if s not in accessible:
            errors.append(f"主讲人不在授权范围内：{s}")

    return errors


def create_activity_api(ctx: SecurityContext, draft: dict, idempotency_key: str) -> dict:
    """Teaching 既有创建 API（模拟）。权限 + 规则 + 幂等都在这里，Agent 无法绕过。"""
    if idempotency_key in _IDEMPOTENCY:
        return {"activity_id": _IDEMPOTENCY[idempotency_key], "deduplicated": True}

    errors = validate_draft(ctx, draft)
    if errors:
        raise BusinessRuleError("；".join(errors))

    activity_id = "act-" + uuid.uuid4().hex[:8]
    _ACTIVITIES[activity_id] = {
        "id": activity_id,
        "tenant": ctx.tenant_id,
        "creator": ctx.user_id,
        "draft": draft,
        "status": "created",
    }
    _IDEMPOTENCY[idempotency_key] = activity_id
    return {"activity_id": activity_id, "deduplicated": False}


def reset_for_test() -> None:
    _ACTIVITIES.clear()
    _IDEMPOTENCY.clear()


def activity_count() -> int:
    return len(_ACTIVITIES)
