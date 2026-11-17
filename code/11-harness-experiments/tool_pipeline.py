#!/usr/bin/env python3
"""tool_pipeline · 工具执行流水线 —— docs/11-harness-engineering/06-tool-engineering.md 代码锚点。

镜像真实 DSH（tool-execution-pipeline.zh.md）的共享调用流水线：
  tool/call（执行前先记录）
    → tools/pre-execute 瀑布（钩子/权限/沙箱，可 allow/deny/ask）
    → 单调守卫（只能 deny 或弃权，不能放行）
    → ctx.approval 一次性审批（缺失/无法回答 → 拒绝，fail-closed）
    → tools/execute 环绕（超时/重试/指标）→ 工具体
    → tools/post-execute 瀑布（接受/拦截/替换/补上下文）
    → tools/result（冻结的权威结果）

关键不变式（本实验逐条断言）：
- tool/call 在执行前记录；tool/result 是唯一面向模型的结论。
- 守卫是单调的：只能拒绝，不能把已被拒的调用放行。
- 审批失败即拒（fail-closed），绝不默认放行。

运行（离线）：../../.venv/bin/python tool_pipeline.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


class Denied(Exception):
    """调用被拒绝（守卫/审批/前置策略）。"""


@dataclass
class ToolPipeline:
    bodies: dict[str, Callable] = field(default_factory=dict)
    pre_hooks: list[Callable] = field(default_factory=list)     # 返回 allow/deny/ask
    guards: list[Callable] = field(default_factory=list)        # 返回 deny/abstain（单调）
    post_hooks: list[Callable] = field(default_factory=list)    # 变换结果
    approval: Callable | None = None                            # ask 时调用；None=fail-closed
    events: list[dict] = field(default_factory=list)
    body_ran: list[str] = field(default_factory=list)

    def register(self, name: str, body: Callable) -> None:
        self.bodies[name] = body

    def execute(self, name: str, args: dict) -> str:
        # 1. 执行前先记录 tool/call（DSH 不变式）
        self.events.append({"kind": "tool_call", "name": name})
        if name not in self.bodies:
            raise Denied(f"工具不在白名单：{name}")

        # 2. pre-execute 瀑布
        verdict = "allow"
        for hook in self.pre_hooks:
            v = hook(name, args)
            if v == "deny":
                verdict = "deny"; break
            if v == "ask":
                verdict = "ask"
        if verdict == "deny":
            self.events.append({"kind": "tool_result", "name": name, "denied": True})
            raise Denied("pre-execute 拒绝")

        # 3. 审批（ask 时）：fail-closed
        if verdict == "ask":
            if self.approval is None or not self.approval(name, args):
                self.events.append({"kind": "tool_result", "name": name, "denied": True})
                raise Denied("审批未通过（fail-closed）")

        # 4. 单调守卫：只能 deny 或弃权
        for guard in self.guards:
            if guard(name, args) == "deny":
                self.events.append({"kind": "tool_result", "name": name, "denied": True})
                raise Denied("守卫拒绝")

        # 5. execute 环绕 + 工具体
        self.body_ran.append(name)
        result = self.bodies[name](args)

        # 6. post-execute 瀑布：可替换结果
        for hook in self.post_hooks:
            result = hook(name, result)

        # 7. 冻结权威结果 tool/result
        self.events.append({"kind": "tool_result", "name": name, "content": result})
        return result


def demo() -> None:
    print("【tool_pipeline】工具执行流水线")
    p = ToolPipeline()
    p.register("query_rules", lambda a: "时长 30~240 分钟")
    p.post_hooks.append(lambda name, r: f"[已审计] {r}")
    print("  正常调用：", p.execute("query_rules", {}))

    print("\n  审批 fail-closed（ask 但无审批器）：")
    p2 = ToolPipeline()
    p2.register("delete_all", lambda a: "已删除")
    p2.pre_hooks.append(lambda n, a: "ask")
    try:
        p2.execute("delete_all", {})
    except Denied as e:
        print("   拒绝 ->", e, "| 工具体是否运行:", "delete_all" in p2.body_ran)

    print("\n  单调守卫拒绝：")
    p3 = ToolPipeline()
    p3.register("query_rules", lambda a: "r")
    p3.guards.append(lambda n, a: "deny" if n == "query_rules" else "abstain")
    try:
        p3.execute("query_rules", {})
    except Denied as e:
        print("   拒绝 ->", e)

    print("\n  事件顺序（tool_call 先于 tool_result）：", [e["kind"] for e in p.events])


def selftest() -> None:
    # 正常 + post 替换 + 事件顺序
    p = ToolPipeline()
    p.register("t", lambda a: "raw")
    p.post_hooks.append(lambda n, r: r + "!")
    assert p.execute("t", {}) == "raw!"
    assert [e["kind"] for e in p.events] == ["tool_call", "tool_result"]
    assert p.events[-1]["content"] == "raw!"          # 冻结的是 post 后的结果

    # pre-deny：工具体不运行
    p2 = ToolPipeline(); p2.register("t", lambda a: "x")
    p2.pre_hooks.append(lambda n, a: "deny")
    try:
        p2.execute("t", {}); raise AssertionError()
    except Denied:
        pass
    assert p2.body_ran == []

    # ask 无审批器 → fail-closed，工具体不运行
    p3 = ToolPipeline(); p3.register("t", lambda a: "x")
    p3.pre_hooks.append(lambda n, a: "ask")
    try:
        p3.execute("t", {}); raise AssertionError()
    except Denied:
        pass
    assert p3.body_ran == []

    # ask + 审批通过 → 运行
    p4 = ToolPipeline(); p4.register("t", lambda a: "x")
    p4.pre_hooks.append(lambda n, a: "ask")
    p4.approval = lambda n, a: True
    assert p4.execute("t", {}) == "x"

    # 单调守卫拒绝
    p5 = ToolPipeline(); p5.register("t", lambda a: "x")
    p5.guards.append(lambda n, a: "deny")
    try:
        p5.execute("t", {}); raise AssertionError()
    except Denied:
        pass
    assert p5.body_ran == []


if __name__ == "__main__":
    demo()
