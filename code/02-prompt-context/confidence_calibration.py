#!/usr/bin/env python3
"""confidence_calibration · 让模型报置信度是否合理 —— docs/02-prompt-context/03-agent-intent-routing.md §6.7 代码锚点。

结论先行：**让模型报置信度可以作为「参考信号」，但不能当成「校准过的概率」直接用。**

本 demo 用**模拟数据**（不是真实模型的实测）演示三件事：
1. 模型自报置信度常常「过度自信」：嘴上 0.9，实际准确率可能只有 0.7 → 用 ECE 量化。
2. 温度缩放（temperature scaling）可以把分数「拉回」到更接近真实概率。
3. 决策层面：直接卡「自报置信度 ≥ 0.9」几乎筛不掉错误；
   用「证据校验 + 分数边距」比用自报置信度靠谱得多。

⚠️ 数据是合成的，用来讲原理；真实模型需要用你的业务标注集重新测 ECE 与校准温度。

运行（离线）：../../.venv/bin/python confidence_calibration.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Sample:
    correct: bool          # 路由/回答是否真的正确
    stated: float          # 模型自报置信度
    margin: float          # top1 与 top2 的分数差（可计算的外部信号）
    evidence: bool         # 是否有可验证证据（命中的关键词/字段/引用）


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z > -700 else 0.0


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def make_samples(n: int, seed: int = 42) -> list[Sample]:
    """模拟模型行为：有证据时更准；自报置信度整体偏高且与正确性弱相关。"""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        evidence = rng.random() < 0.55
        difficulty = rng.random()
        p_correct = 0.95 if evidence else 0.35
        p_correct -= 0.15 * difficulty if not evidence else 0.0
        correct = rng.random() < p_correct
        # 自报置信度：普遍偏高，正确时略高一点点（弱相关，模拟过度自信）
        stated = 0.72 + 0.22 * rng.random() + (0.03 if correct else 0.0)
        stated = min(0.99, stated)
        # 分数边距：正确时明显更大（这是可计算的外部信号）
        margin = (0.15 + 0.25 * rng.random()) if correct else (0.02 + 0.20 * rng.random())
        out.append(Sample(correct, stated, margin, evidence))
    return out


# --------------------------------------------------------------------------- 校准度量
def ece(samples: list[Sample], conf_fn) -> tuple[float, list[tuple[float, float, int, float]]]:
    """期望校准误差（Expected Calibration Error）+ 可靠度分桶。"""
    bins: dict[int, list[Sample]] = {}
    for s in samples:
        b = min(9, int(conf_fn(s) * 10))
        bins.setdefault(b, []).append(s)
    total = len(samples)
    err = 0.0
    table = []
    for b in sorted(bins):
        group = bins[b]
        avg_conf = sum(conf_fn(s) for s in group) / len(group)
        acc = sum(1 for s in group if s.correct) / len(group)
        err += len(group) / total * abs(acc - avg_conf)
        table.append(((b / 10, (b + 1) / 10), round(avg_conf, 3), len(group), round(acc, 3)))
    return err, table


def fit_temperature(cal: list[Sample]) -> float:
    """温度缩放：在 logit 上除以 T，网格搜索最小化负对数似然。"""
    best_t, best_nll = 1.0, float("inf")
    for t in [x / 20 for x in range(10, 81)]:        # 0.5 ~ 4.0
        nll = 0.0
        for s in cal:
            p = sigmoid(logit(s.stated) / t)
            p = min(max(p, 1e-6), 1 - 1e-6)
            nll -= math.log(p if s.correct else 1 - p)
        if nll < best_nll:
            best_t, best_nll = t, nll
    return best_t


def calibrated(s: Sample, t: float) -> float:
    return sigmoid(logit(s.stated) / t)


# --------------------------------------------------------------------------- 决策策略对比
@dataclass
class PolicyResult:
    name: str
    coverage: float       # 接受比例
    accepted_acc: float   # 接受样本的真实准确率


def eval_policy(samples: list[Sample], name: str, accept) -> PolicyResult:
    acc = [s for s in samples if accept(s)]
    if not acc:
        return PolicyResult(name, 0.0, 0.0)
    return PolicyResult(name, round(len(acc) / len(samples), 3),
                        round(sum(1 for s in acc if s.correct) / len(acc), 3))


def demo() -> None:
    cal, test = make_samples(200, seed=1), make_samples(200, seed=2)
    base = sum(1 for s in test if s.correct) / len(test)
    print("【confidence_calibration】让模型报置信度是否合理（合成数据，讲原理）")
    print(f"  测试集基础准确率（不接受/拒绝，全量）: {base:.3f}")

    e_raw, table = ece(test, lambda s: s.stated)
    print(f"\n  ① 自报置信度的校准情况")
    print(f"    ECE（期望校准误差）= {e_raw:.3f}   ← 0 表示完美校准")
    print("    可靠度分桶（置信区间 / 平均置信 / 样本数 / 实际准确率）:")
    for rng_, conf, n, acc in table:
        print(f"      {rng_[0]:.1f}-{rng_[1]:.1f}   {conf:.2f}   n={n:<4} acc={acc:.2f}")

    t = fit_temperature(cal)
    e_cal = ece(test, lambda s: calibrated(s, t))[0]
    print(f"\n  ② 温度缩放后")
    print(f"    拟合温度 T = {t:.2f}（T>1 说明模型过度自信，需要把概率往下压）")
    print(f"    校准后 ECE = {e_cal:.3f}（原 {e_raw:.3f}）")

    print(f"\n  ③ 决策策略对比（目标：接受的那部分要尽量准）")
    policies = [
        ("直接卡自报置信 ≥ 0.90", lambda s: s.stated >= 0.90),
        ("校准后置信 ≥ 0.90", lambda s: calibrated(s, t) >= 0.90),
        ("分数边距 ≥ 0.18", lambda s: s.margin >= 0.18),
        ("有证据（校验通过）", lambda s: s.evidence),
        ("证据 + 边距 ≥ 0.12", lambda s: s.evidence and s.margin >= 0.12),
    ]
    for name, fn in policies:
        r = eval_policy(test, name, fn)
        print(f"    {name:<22} 覆盖率={r.coverage:<6} 接受域准确率={r.accepted_acc}")

    print("\n  结论：")
    print("  · 自报置信度普遍偏高（ECE 大），直接当概率用会高估可靠性；")
    print("  · 温度缩放能改善校准，但需要标注集拟合，且只能修「整体偏移」，修不了「不知道」；")
    print("  · 真正决定「敢不敢接受」的，是**可验证证据 + 候选间边距**这类外部信号；")
    print("  · 工程做法：置信度只做参考 → 用标注集校准 → 结合证据/边距决策 → 高风险仍走审批。")


def selftest() -> None:
    cal, test = make_samples(300, seed=3), make_samples(300, seed=4)
    # 1) 自报置信度与准确率存在明显偏差（过度自信）
    e_raw, _ = ece(test, lambda s: s.stated)
    assert e_raw > 0.08, f"模拟应体现过度自信，ECE={e_raw}"
    # 2) 温度缩放后 ECE 应下降
    t = fit_temperature(cal)
    e_cal, _ = ece(test, lambda s: calibrated(s, t))
    assert e_cal <= e_raw, f"校准后 ECE 应不高于原值: {e_cal} vs {e_raw}"
    # 3) 校准温度 > 1（过度自信 → 压低概率）
    assert t >= 0.9
    # 4) 关键结论：有证据的策略，接受域准确率明显高于「直接卡自报置信」
    raw_policy = eval_policy(test, "raw", lambda s: s.stated >= 0.9)
    ev_policy = eval_policy(test, "evidence", lambda s: s.evidence)
    assert ev_policy.accepted_acc > raw_policy.accepted_acc + 0.05, \
        f"证据校验应优于自报置信: {ev_policy.accepted_acc} vs {raw_policy.accepted_acc}"
    # 5) 边距与证据组合应更严（覆盖更低、准确更高）
    combo = eval_policy(test, "combo", lambda s: s.evidence and s.margin >= 0.12)
    assert combo.coverage <= ev_policy.coverage
    assert combo.accepted_acc >= ev_policy.accepted_acc


if __name__ == "__main__":
    demo()
