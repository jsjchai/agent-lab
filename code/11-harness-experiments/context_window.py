#!/usr/bin/env python3
"""context_window · 上下文工程 —— docs/11-harness-engineering/05-context-engineering.md 代码锚点。

镜像真实 DSH 的上下文管理三机制：
1. **组装（assembly）**：模型上下文 = 系统提示词片段 + 从日志投影的历史 + 注入的运行时上下文。
   （DSH ctx.systemPrompt 组装 + deriveMessages + agent.inject）
2. **压缩（compaction）**：历史超预算时，先剪枝过大的工具结果，再摘要旧轮次。
   （DSH compaction-basic + compaction-tool-result-pruner，在 agent/pre-step 请求前处理）
3. **运行时注入（inject）**：把当前时间/工作目录等事实注入下一次请求，不改写历史。
   （DSH agent.inject → 落到下一次获准请求）

运行（离线）：../../.venv/bin/python context_window.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class ContextEngine:
    system_sections: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)        # 会话日志（真相源）
    injected: list[str] = field(default_factory=list)        # 运行时注入（不进历史）
    budget: int = 200                                        # token 预算（演示用小值）

    def add_event(self, kind: str, content: str) -> None:
        self.events.append({"kind": kind, "content": content})

    def inject(self, fact: str) -> None:
        self.injected.append(fact)                             # agent.inject 类比

    def _project_history(self) -> list[dict]:
        return [{"role": e["kind"], "content": e["content"]} for e in self.events]

    def assemble(self) -> list[dict]:
        """组装模型上下文：系统 + 历史 + 运行时注入（注入在末尾，不改历史）。"""
        msgs = [{"role": "system", "content": "\n".join(self.system_sections)}]
        msgs += self._project_history()
        if self.injected:
            msgs.append({"role": "system", "content": "[运行时上下文] " + "；".join(self.injected)})
        return msgs

    def _size(self, msgs: list[dict]) -> int:
        return sum(est_tokens(m["content"]) for m in msgs)

    def compact(self) -> dict:
        """请求前压缩：先剪枝过大工具结果，再摘要旧轮次（DSH compaction 顺序）。"""
        actions = {"pruned": 0, "summarized": 0}
        # 1. 剪枝过大的工具结果（替换为占位，保留可恢复线索）
        for e in self.events:
            if e["kind"] == "tool" and est_tokens(e["content"]) > 40:
                e["content"] = f"[工具结果已剪枝，原长 {len(e['content'])} 字符，可按事件序号恢复]"
                actions["pruned"] += 1
        # 2. 仍超预算 → 摘要旧轮次（保留最近若干条）
        if self._size(self.assemble()) > self.budget and len(self.events) > 4:
            old, recent = self.events[:-4], self.events[-4:]
            summary = f"[摘要： earlier {len(old)} 条历史，主题={old[0]['content'][:20]}…]"
            self.events = [{"kind": "user", "content": summary}] + recent
            actions["summarized"] = len(old)
        return actions


def demo() -> None:
    print("【context_window】组装 + 压缩 + 注入")
    eng = ContextEngine(system_sections=["你是教学活动助手。"], budget=50)
    eng.add_event("user", "帮我创建数学教研活动")
    eng.add_event("tool", "活动规则：" + "时长须在30到240分钟之间，主讲人1到3位。" * 15)  # 大工具结果
    eng.add_event("assistant", "好的，请问具体日期？")
    eng.add_event("user", "11月20日")
    eng.inject("当前时间 2026-11-17；工作目录 /repo")

    print("  组装后消息数：", len(eng.assemble()), "| 估算 token：", eng._size(eng.assemble()))
    print("  末条（运行时注入）：", eng.assemble()[-1]["content"][:40])
    actions = eng.compact()
    print("  压缩动作：", actions)
    print("  压缩后 token：", eng._size(eng.assemble()), "| 预算：", eng.budget)


def selftest() -> None:
    eng = ContextEngine(system_sections=["sys"], budget=120)
    eng.add_event("user", "u1")
    eng.add_event("tool", "x" * 400)            # 大工具结果
    eng.add_event("assistant", "a1")
    eng.add_event("user", "u2")
    eng.inject("runtime-fact")
    msgs = eng.assemble()
    assert msgs[0]["content"] == "sys"
    assert "runtime-fact" in msgs[-1]["content"]     # 注入在末尾
    assert not any("runtime-fact" in e["content"] for e in eng.events)  # 注入不进历史
    before = eng._size(msgs)
    actions = eng.compact()
    assert actions["pruned"] >= 1                  # 大工具结果被剪枝
    assert eng._size(eng.assemble()) < before      # 压缩后变小
    # 剪枝保留可恢复线索
    assert any("可按事件序号恢复" in e["content"] for e in eng.events)


if __name__ == "__main__":
    demo()
