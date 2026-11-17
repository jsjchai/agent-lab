#!/usr/bin/env python3
"""m09 · 模型部署与路由 —— 对应文档 §9。

文档 §9 的路由维度在这里实现：任务类型 / 数据合规 / 成本 / 延迟 / 故障状态。
核心合规规则：**PRIVATE_ONLY 任务不能因为私有模型故障而自动回退到云端。**

本例用模拟 provider 演示路由 + 熔断 + 合规回退；生产把 provider.invoke
换成真实云 API / vLLM 调用即可（见 common/llm.py 的 openai 后端）。

运行（离线）：
    ../../.venv/bin/python m09_router.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


class ComplianceError(Exception):
    """PRIVATE_ONLY 任务在私有模型不可用时抛出，绝不回退云端。"""


class ProviderDown(Exception):
    pass


@dataclass
class Provider:
    name: str
    kind: str               # cloud / private
    cost_per_1k: float      # 元 / 1k token
    latency_ms: float
    supports: tuple         # 支持的任务类型
    force_fail: bool = False
    fail_count: int = 0
    open_until: float = 0.0  # 熔断打开截止时间

    def invoke(self, task_type: str, tokens: int = 500) -> dict:
        if self.force_fail:
            raise ProviderDown(f"{self.name} 故障")
        return {"provider": self.name, "task": task_type, "tokens": tokens}


class ModelRouter:
    BREAKER_THRESHOLD = 3
    BREAKER_COOLDOWN = 5.0

    def __init__(self, providers: list[Provider]):
        self.providers = {p.name: p for p in providers}
        self.stats: dict[str, dict] = {p.name: {"calls": 0, "failures": 0, "cost": 0.0, "latency": 0.0} for p in providers}

    def _breaker_open(self, p: Provider) -> bool:
        return p.fail_count >= self.BREAKER_THRESHOLD and time.time() < p.open_until

    def _candidates(self, task_type: str, compliance: str) -> list[Provider]:
        pool = [p for p in self.providers.values() if task_type in p.supports and not self._breaker_open(p)]
        if compliance == "PRIVATE_ONLY":
            return [p for p in pool if p.kind == "private"]
        # ALLOW_CLOUD：私有优先（成本低），云端兜底
        return sorted(pool, key=lambda p: (p.kind != "private", p.cost_per_1k))

    def _record_success(self, p: Provider, tokens: int) -> None:
        p.fail_count = 0
        s = self.stats[p.name]
        s["calls"] += 1
        s["cost"] += p.cost_per_1k * tokens / 1000
        s["latency"] += p.latency_ms

    def _record_failure(self, p: Provider) -> None:
        p.fail_count += 1
        self.stats[p.name]["failures"] += 1
        if p.fail_count >= self.BREAKER_THRESHOLD:
            p.open_until = time.time() + self.BREAKER_COOLDOWN

    def call(self, task_type: str, compliance: str = "ALLOW_CLOUD", tokens: int = 500) -> dict:
        candidates = self._candidates(task_type, compliance)
        if not candidates:
            if compliance == "PRIVATE_ONLY":
                raise ComplianceError(f"PRIVATE_ONLY 任务 {task_type} 无可用私有模型，且禁止回退云端")
            raise ProviderDown(f"任务 {task_type} 无可用模型")

        last_err = None
        for p in candidates:
            try:
                result = p.invoke(task_type, tokens)
                self._record_success(p, tokens)
                return result
            except ProviderDown as exc:
                self._record_failure(p)
                last_err = exc
                # PRIVATE_ONLY：私有失败立即终止，不尝试云端
                if compliance == "PRIVATE_ONLY":
                    raise ComplianceError(f"PRIVATE_ONLY 任务私有模型故障，禁止回退云端：{exc}")
        raise ProviderDown(f"所有候选模型失败：{last_err}")


def default_router() -> ModelRouter:
    return ModelRouter([
        Provider("private-qwen", "private", 0.0, 120, ("intent", "extract", "chat", "embed")),
        Provider("cloud-gpt", "cloud", 0.02, 80, ("intent", "extract", "chat", "reason")),
    ])


def demo() -> None:
    print("【m09 模型路由】")
    r = default_router()
    print("  正常路由(intent, ALLOW_CLOUD)：", r.call("intent")["provider"], "(私有优先)")
    print("  复杂推理(reason)：", r.call("reason")["provider"], "(私有不支持->云端)")

    print("\n  私有故障 + PRIVATE_ONLY：")
    r.providers["private-qwen"].force_fail = True
    try:
        r.call("intent", compliance="PRIVATE_ONLY")
        print("    ✗ 不应成功")
    except ComplianceError as exc:
        print("    ✓ 拒绝回退云端 ->", str(exc)[:40])

    print("\n  私有故障 + ALLOW_CLOUD：")
    print("    回退到：", r.call("intent", compliance="ALLOW_CLOUD")["provider"])

    print("\n  熔断演示（连续失败 3 次后打开）：")
    r2 = default_router()
    r2.providers["cloud-gpt"].force_fail = True
    for _ in range(3):
        try:
            r2.call("reason")
        except ProviderDown:
            pass
    print("    cloud-gpt 熔断打开?", r2._breaker_open(r2.providers["cloud-gpt"]))

    print("\n  统计：")
    for name, s in r.stats.items():
        print(f"    {name}: calls={s['calls']} failures={s['failures']} cost={s['cost']:.4f}元")


def selftest() -> None:
    r = default_router()
    assert r.call("intent")["provider"] == "private-qwen"
    assert r.call("reason")["provider"] == "cloud-gpt"

    r.providers["private-qwen"].force_fail = True
    try:
        r.call("intent", compliance="PRIVATE_ONLY")
        raise AssertionError("PRIVATE_ONLY 不应回退")
    except ComplianceError:
        pass
    assert r.call("intent", compliance="ALLOW_CLOUD")["provider"] == "cloud-gpt"

    r2 = default_router()
    r2.providers["cloud-gpt"].force_fail = True
    for _ in range(3):
        try:
            r2.call("reason")
        except ProviderDown:
            pass
    assert r2._breaker_open(r2.providers["cloud-gpt"])


if __name__ == "__main__":
    demo()
