#!/usr/bin/env python3
"""m04 · Tool Calling 与业务工具设计 —— 对应文档 §7。

文档 §7 的安全规则在这里逐条落地：
- 每次工具调用都重新校验身份和权限。
- 不信任模型提供的 userId / tenantId / orgId（出现即拒绝）。
- 工具白名单 + 参数校验 + 调用次数限制。
- P0 不开放发布/审批/删除等写工具（本注册表里根本没有它们）。
- 工具只返回完成任务所需的最小数据，且每次调用有审计记录。

运行（离线）：
    ../../.venv/bin/python m04_tools.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import BaseModel, Field, ValidationError

from common import business
from common.security import AuditLog, AuthError, SecurityContext

# 模型绝不允许自带的身份字段（org_id 是受校验的查询参数，不在此列；
# 它能否访问由 ctx.can_access_org 决定，见 search/rotation handler）
_FORBIDDEN_IDENTITY = {"userId", "tenantId", "user_id", "tenant_id"}


class ToolSpec:
    def __init__(self, name: str, kind: str, params: type[BaseModel],
                 handler: Callable, max_calls: int = 5, description: str = ""):
        self.name = name
        self.kind = kind  # read / validate / compute
        self.params = params
        self.handler = handler
        self.max_calls = max_calls
        self.description = description


class ToolRegistry:
    def __init__(self, audit: AuditLog):
        self._tools: dict[str, ToolSpec] = {}
        self._calls: dict[tuple[str, str], int] = {}
        self.audit = audit

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, ctx: SecurityContext, args: dict, task_id: str = "t") -> Any:
        # 1. 白名单
        spec = self._tools.get(name)
        if spec is None:
            self.audit.record(name, ctx, {"reason": "not in whitelist"}, allowed=False)
            raise AuthError(f"工具不在白名单：{name}")

        # 2. 拒绝模型自带身份字段
        forged = _FORBIDDEN_IDENTITY & set(args)
        if forged:
            self.audit.record(name, ctx, {"reason": "forged identity", "fields": sorted(forged)}, allowed=False)
            raise AuthError(f"工具参数不允许携带身份字段：{sorted(forged)}")

        # 3. 调用次数限制
        key = (task_id, name)
        self._calls[key] = self._calls.get(key, 0) + 1
        if self._calls[key] > spec.max_calls:
            self.audit.record(name, ctx, {"reason": "call limit"}, allowed=False)
            raise AuthError(f"工具调用次数超限：{name}")

        # 4. 参数校验
        try:
            params = spec.params.model_validate(args)
        except ValidationError as exc:
            self.audit.record(name, ctx, {"reason": "bad params"}, allowed=False)
            raise AuthError(f"参数非法：{exc.errors()[0]['msg']}")

        # 5. 执行（handler 内部再做权限校验）+ 审计
        try:
            result = spec.handler(ctx, params)
        except AuthError as exc:
            self.audit.record(name, ctx, {"reason": str(exc)}, allowed=False)
            raise
        self.audit.record(name, ctx, {"kind": spec.kind}, allowed=True)
        return result


# --------------------------------------------------------------------------- 参数模型
class EmptyParams(BaseModel):
    pass


class OrgParams(BaseModel):
    org_id: str = Field(min_length=1)


class SearchParams(BaseModel):
    org_id: str = Field(min_length=1)
    keyword: str = ""


class DraftParams(BaseModel):
    draft: dict


class SlotsParams(BaseModel):
    slots: dict


# --------------------------------------------------------------------------- 工具实现
def build_registry(audit: AuditLog) -> ToolRegistry:
    reg = ToolRegistry(audit)

    reg.register(ToolSpec("query_activity_rules", "read", EmptyParams,
                          lambda ctx, p: business.ACTIVITY_RULES, description="查询活动规则"))

    def rotation(ctx, p: OrgParams):
        if not ctx.can_access_org(p.org_id):
            raise AuthError("无权访问该组织轮转计划")
        return business.ROTATION_SNAPSHOT.get(p.org_id, {})

    reg.register(ToolSpec("query_rotation_snapshot", "read", OrgParams, rotation, description="查询轮转计划快照"))

    reg.register(ToolSpec("query_org_scope", "read", EmptyParams,
                          lambda ctx, p: {"org_ids": list(ctx.org_ids)}, description="查询当前用户可访问组织"))

    def search(ctx, p: SearchParams):
        if not ctx.can_access_org(p.org_id):
            raise AuthError("无权在该组织搜索人员")
        people = business.PARTICIPANTS.get(p.org_id, [])
        if p.keyword:
            people = [x for x in people if p.keyword in x]
        return {"participants": people}  # 最小数据：只返回姓名

    reg.register(ToolSpec("search_participants", "read", SearchParams, search, description="授权范围内搜索人员"))

    reg.register(ToolSpec("validate_activity_draft", "validate", DraftParams,
                          lambda ctx, p: {"errors": business.validate_draft(ctx, p.draft)}, description="校验活动草稿"))

    def build(ctx, p: SlotsParams):
        s = p.slots
        return {
            "title": f"{s.get('grade', '')}{s.get('subject', '')}{s.get('activity_type', '教学活动')}",
            "activity_type": s.get("activity_type", "教研活动"),
            "subject": s.get("subject", ""),
            "grade": s.get("grade"),
            "date_text": s.get("date_text", ""),
            "audience": s.get("audience", ""),
            "speakers": s.get("speakers", []),
            "duration_minutes": s.get("duration_minutes", 90),
        }

    reg.register(ToolSpec("build_activity_draft", "compute", SlotsParams, build, description="构建活动草稿"))
    return reg


def demo() -> None:
    from common.security import authenticate

    print("【m04 业务工具】白名单:", )
    audit = AuditLog()
    reg = build_registry(audit)
    print("  ", reg.names())
    ctx = authenticate("u1")

    print("\n  正常调用 search_participants(o1)：", reg.call("search_participants", ctx, {"org_id": "o1", "keyword": "张"}))
    print("  查询组织范围：", reg.call("query_org_scope", ctx, {}))

    print("\n  安全拦截测试：")
    for label, fn in [
        ("跨租户搜索(o3)", lambda: reg.call("search_participants", ctx, {"org_id": "o3"})),
        ("伪造身份字段", lambda: reg.call("query_org_scope", ctx, {"userId": "admin"})),
        ("白名单外工具", lambda: reg.call("publish_activity", ctx, {})),
        ("非法参数", lambda: reg.call("search_participants", ctx, {"org_id": ""})),
    ]:
        try:
            fn()
            print(f"    ✗ {label} 未被拦截")
        except AuthError as exc:
            print(f"    ✓ {label} 被拦截 -> {exc}")

    print(f"\n  审计记录 {len(audit.entries)} 条，其中拒绝 {len(audit.denied())} 条")


def selftest() -> None:
    from common.security import authenticate

    audit = AuditLog()
    reg = build_registry(audit)
    ctx = authenticate("u1")

    assert reg.call("search_participants", ctx, {"org_id": "o1"})["participants"]
    for bad in [
        lambda: reg.call("search_participants", ctx, {"org_id": "o3"}),
        lambda: reg.call("query_org_scope", ctx, {"tenantId": "t2"}),
        lambda: reg.call("delete_activity", ctx, {}),
    ]:
        try:
            bad()
            raise AssertionError("应当被拦截")
        except AuthError:
            pass
    assert len(audit.denied()) >= 3
    # 写工具根本不存在
    assert "publish_activity" not in reg.names()


if __name__ == "__main__":
    demo()
