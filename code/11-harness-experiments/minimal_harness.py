#!/usr/bin/env python3
"""minimal_harness · 最小 Agent Harness —— docs/11-harness-engineering 的代码锚点。

用 ~150 行 Python 实现一个 Harness 的核心骨架，镜像 DeepSeek Harness 的关键设计：
- **会话日志即真相**：append-only 事件日志，模型历史从日志投影（derive_messages）。
- **工具注册表 + 带把关的执行流水线**：register / pre-execute / execute / post-execute。
- **Agent Loop**：step = 一次模型请求 + 它调用的工具；turn = 若干 step，直到不再欠工作。
- **停止条件**：模型不再调工具，或达到 max_steps（防无限循环）。

这是教学骨架，不是 DSH 本身；DSH 用 Cordis 插件把每一部分做成可替换副作用。
对照阅读：docs/11-harness-engineering/01-introduction.md。

运行（离线，无需 key）：
    ../../.venv/bin/python minimal_harness.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable


# --------------------------------------------------------------------------- 会话日志
@dataclass
class EventLog:
    """append-only 事件日志（DSH core/session 的极简类比）。

    DSH 原则「模型可见即已记录」：模型看到的上下文必须能从日志重建。
    这里只保留模型可见消息事件，演示 derive_messages 投影。
    """
    events: list[dict] = field(default_factory=list)

    def append(self, kind: str, **payload) -> None:
        self.events.append({"kind": kind, **payload})

    def derive_messages(self) -> list[dict]:
        """从日志投影模型历史（DSH deriveMessages 的类比）。"""
        msgs = []
        for e in self.events:
            if e["kind"] == "system":
                msgs.append({"role": "system", "content": e["content"]})
            elif e["kind"] == "user":
                msgs.append({"role": "user", "content": e["content"]})
            elif e["kind"] == "assistant":
                msgs.append({"role": "assistant", "content": e["content"]})
            elif e["kind"] == "tool_result":
                msgs.append({"role": "tool", "name": e["name"], "content": e["content"]})
        return msgs


# --------------------------------------------------------------------------- 工具注册表
@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[[dict], str]


class ToolRegistry:
    """作用域工具注册表 + 带把关的执行流水线（DSH core/tools 的类比）。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self.calls: list[str] = []

    def register(self, name: str, description: str, handler: Callable[[dict], str]) -> None:
        self._tools[name] = Tool(name, description, handler)

    def schemas(self) -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    def execute(self, name: str, args: dict) -> str:
        # pre-execute 把关：白名单
        if name not in self._tools:
            raise ValueError(f"工具不在白名单：{name}")
        self.calls.append(name)
        result = self._tools[name].handler(args)   # execute
        return result                              # post-execute 可在此变换结果


# --------------------------------------------------------------------------- 模型（mock）
def mock_model(messages: list[dict], tools: list[dict]) -> dict:
    """确定性模型替身：先调工具查规则，再据此回答。

    返回 {"tool_call": {name, args}} 或 {"answer": str}。
    真实 Harness 这里接 LLM 适配器（DSH ctx.llm / llm/stream）。
    """
    has_tool_result = any(m["role"] == "tool" for m in messages)
    if not has_tool_result:
        return {"tool_call": {"name": "query_rules", "args": {}}}
    rule = next(m["content"] for m in messages if m["role"] == "tool")
    return {"answer": f"根据规则：{rule}，活动时长应设为 90 分钟。"}


# --------------------------------------------------------------------------- Agent Loop
class Harness:
    """最小 Agent Loop（DSH core/agent-loop 的类比）。"""

    def __init__(self, model: Callable, tools: ToolRegistry, system: str, max_steps: int = 6):
        self.model = model
        self.tools = tools
        self.log = EventLog()
        self.system = system
        self.max_steps = max_steps

    def run_turn(self, user_input: str) -> str:
        self.log.append("system", content=self.system)
        self.log.append("user", content=user_input)
        steps = 0
        while steps < self.max_steps:
            steps += 1
            # 组装上下文：从日志投影历史 + 工具 schema（DSH system-prompt 组装的类比）
            messages = self.log.derive_messages()
            decision = self.model(messages, self.tools.schemas())
            if "tool_call" in decision:
                call = decision["tool_call"]
                self.log.append("assistant", content=f"[调用工具 {call['name']}]")
                result = self.tools.execute(call["name"], call["args"])
                self.log.append("tool_result", name=call["name"], content=result)
                continue                       # 工具欠下另一次请求 → 下一 step
            answer = decision["answer"]
            self.log.append("assistant", content=answer)
            return answer                      # 不再欠工作 → 关闭轮次
        raise RuntimeError("达到 max_steps，疑似无限循环")


# --------------------------------------------------------------------------- 演示 / 自检
def build_demo_harness() -> Harness:
    tools = ToolRegistry()
    tools.register("query_rules", "查询活动规则", lambda args: "时长须在 30~240 分钟")
    return Harness(mock_model, tools, system="你是教学活动助手。", max_steps=6)


def demo() -> None:
    print("【minimal_harness】最小 Agent Harness 骨架")
    h = build_demo_harness()
    answer = h.run_turn("帮我设一个数学教研活动的时长")
    print("  最终回答：", answer)
    print("  工具调用：", h.tools.calls)
    print("  事件日志（模型可见即已记录）：")
    for e in h.log.events:
        print("   ", e["kind"], "->", str(e.get("content", e.get("name")))[:40])
    print("  从日志重建的模型历史条数：", len(h.log.derive_messages()))


def selftest() -> None:
    h = build_demo_harness()
    answer = h.run_turn("帮我设一个数学教研活动的时长")
    assert "90 分钟" in answer
    assert h.tools.calls == ["query_rules"]                 # 工具确实被调用
    assert any(e["kind"] == "tool_result" for e in h.log.events)
    # 会话日志即真相：历史可完全从日志重建
    msgs = h.log.derive_messages()
    assert msgs[0]["role"] == "system" and msgs[-1]["role"] == "assistant"
    assert len(msgs) == len([e for e in h.log.events if e["kind"] in ("system", "user", "assistant", "tool_result")])
    # 白名单把关
    try:
        h.tools.execute("delete_all", {})
        raise AssertionError("应被拦截")
    except ValueError:
        pass


if __name__ == "__main__":
    demo()
