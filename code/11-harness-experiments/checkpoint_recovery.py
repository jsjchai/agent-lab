#!/usr/bin/env python3
"""checkpoint_recovery · 错误恢复与 Checkpoint —— docs/11-harness-engineering/08-error-recovery.md 代码锚点。

镜像真实 DSH 的可靠性设计（architecture.zh.md / agent-lifecycle.zh.md）：
- **会话日志持久化**：每步事实落盘，进程重启后从日志恢复（DSH session-persistence + fork/resume）。
- **先记录后执行**：tool/call 在执行前记录；若执行中途崩溃，日志里留下「悬空调用」。
- **修复缺失结果**：恢复时检测「有 tool/call 无 tool/result」，补记缺失结果，再继续。
  （DSH「失败步骤会记录缺失的工具结果」）

本实验用 JSON 字符串模拟持久日志，演示「崩溃→重启→修复→续跑」。
业务对照：teaching-agent/m05 的 SqliteSaver + m10 的租约回收。

运行（离线）：../../.venv/bin/python checkpoint_recovery.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


class SimulatedCrash(Exception):
    """模拟进程在工具执行中途硬中断。"""


@dataclass
class DurableLog:
    """持久会话日志（用 JSON 模拟落盘）。"""
    events: list[dict] = field(default_factory=list)

    def append(self, kind: str, **kw) -> None:
        self.events.append({"kind": kind, **kw})

    def save(self) -> str:
        return json.dumps(self.events, ensure_ascii=False)

    @classmethod
    def load(cls, blob: str) -> "DurableLog":
        return cls(events=json.loads(blob))

    def dangling_calls(self) -> list[str]:
        """有 tool/call 但无对应 tool/result 的悬空调用。"""
        called = [e["name"] for e in self.events if e["kind"] == "tool_call"]
        settled = {e["name"] for e in self.events if e["kind"] == "tool_result"}
        return [n for n in called if n not in settled]


def run(log: DurableLog, tools: dict, crash_at: str | None = None) -> str:
    """执行循环；crash_at 指定在哪个工具执行中途崩溃（已记录 tool/call 之后）。"""
    log.append("turn_start")
    log.append("user", content="安排活动")
    for name in tools:
        log.append("tool_call", name=name)          # 先记录
        if name == crash_at:
            raise SimulatedCrash(f"在 {name} 执行中途崩溃")   # 后执行（此处崩溃）
        log.append("tool_result", name=name, content=tools[name]())
    log.append("assistant", content="完成")
    log.append("turn_end", reason="natural")
    return "完成"


def repair(log: DurableLog) -> list[str]:
    """恢复第一步：为悬空调用补记缺失结果（DSH 失败步骤记录缺失工具结果）。"""
    repaired = []
    for name in log.dangling_calls():
        log.append("tool_result", name=name, content="[中断，结果缺失]", interrupted=True)
        repaired.append(name)
    return repaired


def demo() -> None:
    print("【checkpoint_recovery】崩溃 → 重启 → 修复 → 续跑")
    tools = {"query_rules": lambda: "规则OK", "query_people": lambda: "人员OK"}

    log = DurableLog()
    try:
        run(log, tools, crash_at="query_people")
    except SimulatedCrash as e:
        print("  崩溃：", e)
    blob = log.save()                                # 落盘
    print("  悬空调用：", log.dangling_calls())

    print("  --- 进程重启（从持久日志恢复）---")
    log2 = DurableLog.load(blob)                     # 新进程读同一份日志
    repaired = repair(log2)
    print("  修复缺失结果：", repaired)
    print("  修复后悬空：", log2.dangling_calls())
    # 续跑剩余工具
    done = {e["name"] for e in log2.events if e["kind"] == "tool_result" and not e.get("interrupted")}
    for name in tools:
        if name not in done:
            log2.append("tool_call", name=name)
            log2.append("tool_result", name=name, content=tools[name]())
    log2.append("turn_end", reason="recovered")
    print("  恢复后 turn_end：", log2.events[-1]["reason"])


def selftest() -> None:
    tools = {"a": lambda: "ra", "b": lambda: "rb"}
    log = DurableLog()
    try:
        run(log, tools, crash_at="b"); raise AssertionError("应崩溃")
    except SimulatedCrash:
        pass
    assert log.dangling_calls() == ["b"]             # b 悬空
    blob = log.save()
    log2 = DurableLog.load(blob)                     # 重启恢复
    assert log2.dangling_calls() == ["b"]            # 持久日志保留悬空事实
    assert repair(log2) == ["b"]
    assert log2.dangling_calls() == []               # 修复后无悬空
    assert any(e.get("interrupted") for e in log2.events)  # 缺失结果被标记
    # 正常路径无悬空
    log3 = DurableLog()
    assert run(log3, tools) == "完成"
    assert log3.dangling_calls() == []


if __name__ == "__main__":
    demo()
