#!/usr/bin/env python3
"""planning_demo · 模型做规划：Plan-and-Execute vs ReAct vs 失败重规划（医教场景）
—— docs/05-planning/01-planning-with-models.md 与 02-plan-validation-and-replan.md 的代码锚点。

任务：组织一次「全院心肺复苏（CPR）技能考核」。这是一个典型的多步骤长任务：
确定范围 → 查实训室 → 预约 → 通知 → 准备考核表 → 安排督导 → 归档。

本 demo 对照三种规划范式：
1. **Plan-and-Execute**：先一次性生成带依赖的计划，再按拓扑序执行。
2. **ReAct**：不预先生成完整计划，边走边看（think → act → observe），直到完成。
3. **失败重规划（Replan）**：执行中某步失败 → 插入补救步骤 → 继续，而不是整体重来。

并演示计划校验：未知工具、循环依赖、步骤数上限。

运行（离线 mock）：../../.venv/bin/python planning_demo.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- 工具（mock）
TOOL_COST = {  # 名称 -> (模拟 token, 模拟耗时秒)
    "determine_scope": (120, 0.2),
    "check_room": (80, 0.1),
    "book_room": (60, 0.3),
    "notify": (100, 0.4),
    "prepare_form": (90, 0.2),
    "assign_supervisor": (110, 0.3),
    "archive": (70, 0.2),
    "use_backup_room": (60, 0.3),
}


def run_tool(name: str, fail: set[str] | None = None) -> str:
    if fail and name in fail:
        raise RuntimeError(f"工具 {name} 执行失败（模拟：资源不可用）")
    return f"{name} 完成"


# --------------------------------------------------------------------------- 计划结构
@dataclass
class Step:
    id: str
    tool: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"      # pending/running/done/failed/skipped

    def label(self) -> str:
        return f"{self.id}:{self.tool}"


class PlanError(Exception):
    pass


def validate_plan(steps: list[Step], tools: dict, max_steps: int = 12) -> None:
    """计划校验：未知工具、步骤上限、循环依赖。"""
    ids = {s.id for s in steps}
    if len(steps) > max_steps:
        raise PlanError(f"步骤数 {len(steps)} 超过上限 {max_steps}")
    for s in steps:
        if s.tool not in tools:
            raise PlanError(f"未知工具：{s.tool}")
        for dep in s.depends_on:
            if dep not in ids:
                raise PlanError(f"{s.id} 依赖不存在的步骤 {dep}")
    # 循环依赖检测（DFS 三色）
    state: dict[str, int] = {}

    def dfs(node: str) -> None:
        if state.get(node) == 1:
            raise PlanError(f"检测到循环依赖：{node}")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in next(s.depends_on for s in steps if s.id == node):
            dfs(dep)
        state[node] = 2

    for s in steps:
        dfs(s.id)


def topo_order(steps: list[Step]) -> list[Step]:
    """按依赖拓扑排序（同层保持声明顺序）。"""
    idx = {s.id: i for i, s in enumerate(steps)}
    done: set[str] = set()
    order: list[Step] = []
    remaining = list(steps)
    while remaining:
        ready = [s for s in remaining if all(d in done for d in s.depends_on)]
        if not ready:
            raise PlanError("无法拓扑排序（可能存在循环）")
        ready.sort(key=lambda s: idx[s.id])
        s = ready[0]
        order.append(s)
        done.add(s.id)
        remaining.remove(s)
    return order


# --------------------------------------------------------------------------- 规划器（mock）
def plan_cpr_assessment() -> list[Step]:
    """一次性生成带依赖的计划（Plan-and-Execute 的 plan 阶段）。"""
    return [
        Step("s1", "determine_scope"),
        Step("s2", "check_room"),
        Step("s3", "book_room", ["s1", "s2"]),
        Step("s4", "notify", ["s3"]),
        Step("s5", "prepare_form", ["s1"]),
        Step("s6", "assign_supervisor", ["s4"]),
        Step("s7", "archive", ["s5", "s6"]),
    ]


# --------------------------------------------------------------------------- 执行器
@dataclass
class RunStats:
    steps: int = 0
    llm_calls: int = 1          # 规划 1 次
    tokens: int = 200           # 规划消耗
    replans: int = 0
    failed: int = 0

    def add_tool(self, name: str) -> None:
        tok, _ = TOOL_COST.get(name, (50, 0.2))
        self.steps += 1
        self.tokens += tok


def execute_plan(steps: list[Step], fail: set[str] | None = None,
                 replanner=None) -> tuple[list[Step], RunStats, list[str]]:
    """按依赖就绪顺序执行；某步失败时可调用 replanner 返回补救步骤。

    说明：被补救替代的原步骤标记为 skipped；依赖它的步骤把 skipped 视为已满足
    （因为补救步骤已承担该前置工作）。这是演示用的简化建模。
    """
    stats = RunStats()
    log: list[str] = []
    idx = {s.id: i for i, s in enumerate(steps)}
    while True:
        pending = [s for s in steps if s.status == "pending"]
        if not pending:
            break
        ready = [
            s for s in pending
            if all(
                next(x for x in steps if x.id == d).status in ("done", "skipped")
                for d in s.depends_on
            )
        ]
        if not ready:
            raise PlanError("没有可执行的就绪步骤（依赖未满足或循环）")
        ready.sort(key=lambda s: idx.get(s.id, 10**6))
        s = ready[0]
        try:
            run_tool(s.tool, fail)
            s.status = "done"
            stats.add_tool(s.tool)
            log.append(f"✓ {s.label()}")
        except RuntimeError as exc:
            stats.failed += 1
            log.append(f"✗ {s.label()} — {exc}")
            if replanner is None:
                s.status = "failed"
                raise
            stats.llm_calls += 1          # 重规划也是一次模型调用
            stats.tokens += 150
            stats.replans += 1
            new_steps = replanner(s, steps)
            if not new_steps:
                s.status = "failed"
                raise
            s.status = "skipped"          # 原步骤跳过，由补救步骤替代
            log.append(f"↺ 重规划：{s.label()} → {[n.label() for n in new_steps]}")
            pos = steps.index(s) + 1      # 补救步骤紧接着失败步骤执行
            for ns in new_steps:
                if ns.id not in {x.id for x in steps}:
                    steps.insert(pos, ns)
                    pos += 1
            idx = {x.id: i for i, x in enumerate(steps)}
    return steps, stats, log


def replan_on_room_failure(failed: Step, steps: list[Step]) -> list[Step]:
    """补救策略：实训室不可用 → 改用备用实训室，并重排其后依赖。"""
    if failed.tool != "check_room":
        return []
    return [Step("s2b", "use_backup_room", [])]


# --------------------------------------------------------------------------- ReAct（边走边看）
def react_run(task: str, fail: set[str] | None = None) -> tuple[list[str], RunStats]:
    """不预先生成完整计划：每轮 think → act → observe，直到判定完成。"""
    stats = RunStats(llm_calls=0)
    trace: list[str] = []
    # 脚本化的「思考规则」：按依赖决定下一步该做什么（演示用，非模型）
    done: set[str] = set()
    order_tools = ["determine_scope", "check_room", "book_room", "prepare_form",
                   "notify", "assign_supervisor", "archive"]
    for tool in order_tools:
        stats.llm_calls += 1          # 每步一次模型判断
        stats.tokens += 80
        trace.append(f"think: 下一步应执行 {tool}")
        try:
            run_tool(tool, fail)
            done.add(tool)
            stats.add_tool(tool)
            trace.append(f"act: {tool} → observe: 成功")
        except RuntimeError as exc:
            trace.append(f"act: {tool} → observe: 失败（{exc}）")
            trace.append("think: 改用备用实训室")
            run_tool("use_backup_room", None)
            stats.add_tool("use_backup_room")
            stats.llm_calls += 1
    return trace, stats


# --------------------------------------------------------------------------- 演示 / 自检
TOOLS = set(TOOL_COST)


def demo() -> None:
    print("【planning_demo · 医教】模型做规划：Plan-and-Execute / ReAct / 重规划")

    print("\n  ── 1) Plan-and-Execute：先规划，再按依赖执行 ──")
    steps = plan_cpr_assessment()
    validate_plan(steps, TOOLS)
    print("  计划：")
    for s in steps:
        print(f"    {s.label():28s} <- {s.depends_on or '无依赖'}")
    steps, stats, log = execute_plan(steps, fail=None)
    print("  执行：", " → ".join(log))
    print(f"  统计：步骤={stats.steps} 模型调用={stats.llm_calls} token≈{stats.tokens}")

    print("\n  ── 2) 执行失败 → 重规划（不是整体重来）──")
    steps2 = plan_cpr_assessment()
    steps2, stats2, log2 = execute_plan(steps2, fail={"check_room"},
                                        replanner=replan_on_room_failure)
    for line in log2:
        print("   ", line)
    print(f"  统计：步骤={stats2.steps} 重规划={stats2.replans} 模型调用={stats2.llm_calls}")

    print("\n  ── 3) ReAct：边走边看 ──")
    trace, stats3 = react_run("组织 CPR 考核", fail={"check_room"})
    for line in trace[:6]:
        print("   ", line)
    print("    ...")
    print(f"  统计：模型调用={stats3.llm_calls} token≈{stats3.tokens}")

    print("\n  ── 4) 计划校验：坏计划会被拒绝 ──")
    for bad, label in [
        ([Step("a", "determine_scope", ["b"]), Step("b", "check_room", ["a"])], "循环依赖"),
        ([Step("a", "not_a_tool")], "未知工具"),
        ([Step(f"s{i}", "determine_scope") for i in range(20)], "超过步骤上限"),
    ]:
        try:
            validate_plan(bad, TOOLS)
            print(f"    {label}: 未拦截（错误！）")
        except PlanError as exc:
            print(f"    {label}: 拒绝 -> {exc}")

    print("\n  关键结论：")
    print("  · Plan-and-Execute 模型调用少、可预演、便于人工审计划，但计划僵化；")
    print("  · ReAct 灵活、适应观察，但每步都要调模型，成本高、易打转；")
    print("  · 失败时用「重规划」局部修补，比整体重来省 token；前提是计划可校验、步骤可追踪。")


def selftest() -> None:
    # 计划结构与依赖
    steps = plan_cpr_assessment()
    validate_plan(steps, TOOLS)
    order = [s.id for s in topo_order(steps)]
    assert order[0] == "s1" and order[-1] == "s7"
    assert order.index("s3") > order.index("s1") and order.index("s3") > order.index("s2")
    assert order.index("s7") > order.index("s5") and order.index("s7") > order.index("s6")
    # 正常执行
    steps, stats, log = execute_plan(steps, fail=None)
    assert all(s.status == "done" for s in steps)
    assert stats.steps == 7 and stats.llm_calls == 1
    # 失败重规划
    steps2, stats2, log2 = execute_plan(plan_cpr_assessment(), fail={"check_room"},
                                        replanner=replan_on_room_failure)
    assert stats2.replans == 1
    assert any(s.tool == "use_backup_room" and s.status == "done" for s in steps2)
    assert any(s.status == "skipped" for s in steps2)          # 原步骤被跳过
    # 无 replanner 时失败应抛出
    try:
        execute_plan(plan_cpr_assessment(), fail={"check_room"}); raise AssertionError()
    except RuntimeError:
        pass
    # 计划校验
    for bad in (  # 循环
        [Step("a", "determine_scope", ["b"]), Step("b", "check_room", ["a"])],
        [Step("a", "not_a_tool")],                              # 未知工具
        [Step(f"s{i}", "determine_scope") for i in range(20)],  # 超上限
    ):
        try:
            validate_plan(bad, TOOLS); raise AssertionError(f"应拒绝: {bad[:1]}")
        except PlanError:
            pass
    # ReAct 能完成并记录观察
    trace, stats3 = react_run("组织 CPR 考核", fail={"check_room"})
    assert stats3.steps >= 7
    assert any("observe: 失败" in t for t in trace)


if __name__ == "__main__":
    demo()
