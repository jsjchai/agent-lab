#!/usr/bin/env python3
"""execution_loop · Agent 执行循环深入 —— docs/11-harness-engineering/04-execution-loop.md 代码锚点。

在 minimal_harness 基础上，演示真实 Harness（DSH core/agent-loop）的四个关键机制：
1. **step/turn 事件轨迹**：turn_start → step_start → ... → step_end → turn_end，全程可回放。
2. **取消（cancellation）**：signal 触发后，循环在安全点停止，不提交半截请求。
3. **重试（retry）**：模型请求失败记为 attempt，在打开的 step 内重试，不重复组装。
4. **停止条件**：模型不再调工具自然停止；max_steps 硬上限防死循环。

对照真实 DSH：agent-lifecycle.zh.md 的时序图（turn/start → step/start → llm/stream →
tool/call → tool/result → step/end → turn/end；失败记 assistant/attempt 后 agent/request-error 重试）。

运行（离线）：../../.venv/bin/python execution_loop.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CancelSignal:
    """取消信号（DSH 用 AbortSignal；此处极简类比）。"""
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class Loop:
    model: Callable
    tools: dict[str, Callable]
    max_steps: int = 8
    max_retries: int = 2
    events: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)

    def emit(self, kind: str, **kw) -> None:
        self.events.append({"kind": kind, **kw})

    def run_turn(self, user_input: str, signal: CancelSignal | None = None) -> str:
        signal = signal or CancelSignal()
        self.emit("turn_start")
        self.history.append({"role": "user", "content": user_input})
        steps = 0
        while steps < self.max_steps:
            # 安全点检查取消：不提交半截请求（DSH：取消期间不提交 system/users）
            if signal.cancelled:
                self.emit("turn_end", reason="cancelled")
                return "[已取消]"
            steps += 1
            self.emit("step_start", step=steps)

            # 模型请求 + 重试（失败记 attempt，在打开的 step 内重试）
            decision = None
            for attempt in range(self.max_retries + 1):
                try:
                    decision = self.model(self.history, list(self.tools))
                    break
                except Exception as exc:
                    self.emit("attempt", step=steps, error=str(exc))
                    if attempt == self.max_retries:
                        self.emit("step_end", step=steps, status="error")
                        self.emit("turn_end", reason="error")
                        raise
            if "tool_call" in decision:
                name = decision["tool_call"]
                self.emit("tool_call", step=steps, name=name)
                result = self.tools[name]({})
                self.history.append({"role": "tool", "name": name, "content": result})
                self.emit("tool_result", step=steps, name=name)
                self.emit("step_end", step=steps, status="tool")
                continue                                  # 欠一次回填 → 下一 step
            answer = decision["answer"]
            self.history.append({"role": "assistant", "content": answer})
            self.emit("step_end", step=steps, status="answer")
            self.emit("turn_end", reason="natural")
            return answer
        self.emit("turn_end", reason="max_steps")
        raise RuntimeError("达到 max_steps")


# --------------------------------------------------------------------------- 演示模型
def make_flaky_model(fail_first: bool = True):
    """第一次请求抛错（演示重试），之后：先调两个工具再回答（演示多 step）。"""
    state = {"calls": 0, "failed": False}

    def model(history, tools):
        state["calls"] += 1
        if fail_first and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("模型超时")
        tool_results = [m for m in history if m["role"] == "tool"]
        if len(tool_results) < 2:
            return {"tool_call": tools[len(tool_results)]}    # 依次调 tools[0], tools[1]
        return {"answer": "综合两条查询结果，活动时长设为 90 分钟。"}

    return model


def demo() -> None:
    print("【execution_loop】step/turn 轨迹 + 重试 + 多步")
    tools = {"query_rules": lambda a: "时长 30~240 分钟", "query_people": lambda a: "主讲人张三可用"}
    loop = Loop(make_flaky_model(), tools)
    answer = loop.run_turn("帮我安排数学教研活动")
    print("  回答：", answer)
    print("  事件轨迹：")
    for e in loop.events:
        extra = e.get("name") or e.get("error") or e.get("reason") or e.get("status") or ""
        print(f"    {e['kind']:12s} {extra}")

    print("\n  取消演示：")
    sig = CancelSignal()
    loop2 = Loop(make_flaky_model(fail_first=False), tools)
    sig.cancel()                                   # 启动前已取消
    print("   ", loop2.run_turn("任意", sig), "| turn_end 原因:", loop2.events[-1]["reason"])


def selftest() -> None:
    tools = {"query_rules": lambda a: "r", "query_people": lambda a: "p"}
    loop = Loop(make_flaky_model(), tools)
    answer = loop.run_turn("x")
    assert "90 分钟" in answer
    kinds = [e["kind"] for e in loop.events]
    assert kinds[0] == "turn_start" and kinds[-1] == "turn_end"
    assert kinds.count("step_start") == 3            # 重试不额外计 step：2 工具 + 1 回答
    assert "attempt" in kinds                        # 失败被记录
    assert kinds.count("tool_result") == 2
    assert loop.events[-1]["reason"] == "natural"
    # 取消
    sig = CancelSignal(); sig.cancel()
    loop2 = Loop(make_flaky_model(False), tools)
    assert loop2.run_turn("x", sig) == "[已取消]"
    assert loop2.events[-1]["reason"] == "cancelled"
    # max_steps 硬上限
    loop3 = Loop(lambda h, t: {"tool_call": t[0]}, tools, max_steps=3)
    try:
        loop3.run_turn("x"); raise AssertionError("应触发上限")
    except RuntimeError:
        pass
    assert loop3.events[-1]["reason"] == "max_steps"


if __name__ == "__main__":
    demo()
