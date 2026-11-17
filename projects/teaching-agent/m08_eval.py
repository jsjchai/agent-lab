#!/usr/bin/env python3
"""m08 · 评测与质量门禁 —— 对应文档 §12。

读取 golden_set.jsonl（30 条种子用例），用**确定性断言**评测，
对照文档 §12 的初始门槛输出指标。LLM-as-Judge 只辅助表达质量，
业务规则/权限/数据一致性必须用确定性断言——本例全部是确定性断言。

文档要求 ≥100 条 Golden Set；这里给 30 条种子 + 扩展方法（见 README）。

运行（离线）：
    ../../.venv/bin/python m08_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import m02_intent_slots as m02
import m04_tools as m04
import m06_rag as m06
from common import business
from common.llm import LLM
from common.security import AuditLog, AuthError, authenticate

GOLDEN = Path(__file__).resolve().parent / "golden_set.jsonl"

# 文档 §12 初始门槛（需 POC 实测校准）
THRESHOLDS = {
    "意图槽位准确率": 0.90,
    "草稿字段完整率": 0.95,
    "业务规则校验正确率": 0.98,
    "引用准确率": 0.95,
    "无依据拒答率": 0.95,
    "越权拦截率": 1.00,
}


def load_cases() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(verbose: bool = False) -> dict:
    llm = LLM()
    reg = m04.build_registry(AuditLog())
    index = m06.KnowledgeIndex(llm)
    index.build()

    buckets: dict[str, list[bool]] = {k: [] for k in THRESHOLDS}
    details = []

    for case in load_cases():
        cat = case["category"]
        ok = False
        if cat in ("intent_normal", "intent_missing"):
            result = m02.recognize(llm, case["input"])
            missing = set(result.get("missingFields", []))
            ok = set(case["expect_missing"]).issubset(missing)
            if cat == "intent_normal":
                ok = ok and not missing
                buckets["意图槽位准确率"].append(ok)
                # 草稿字段完整率：用槽位构建草稿，检查必填字段
                draft = reg.call("build_activity_draft", authenticate("u1"), {"slots": result.get("slots", {})}, task_id=case["id"])
                complete = all(draft.get(f) for f in ("activity_type", "subject", "date_text", "audience", "speakers"))
                buckets["草稿字段完整率"].append(complete)
            else:
                buckets["意图槽位准确率"].append(ok)
        elif cat in ("validation_illegal", "validation_legal"):
            ctx = authenticate(case["user"])
            errors = business.validate_draft(ctx, case["draft"])
            ok = bool(errors) if cat == "validation_illegal" else not errors
            buckets["业务规则校验正确率"].append(ok)
        elif cat == "knowledge_answerable":
            ans = index.answer(authenticate(case["user"]), case["input"])
            ok = bool(ans["citations"]) and set(ans["citations"]).issubset(set(ans["retrieved"]))
            buckets["引用准确率"].append(ok)
        elif cat == "knowledge_unanswerable":
            ans = index.answer(authenticate(case["user"]), case["input"])
            ok = not ans["citations"] and "无法确认" in ans["answer"]
            buckets["无依据拒答率"].append(ok)
        elif cat == "security_cross_tenant":
            ctx = authenticate(case["user"])
            try:
                reg.call(case["tool"], ctx, case["args"])
                ok = False
            except AuthError:
                ok = True
            buckets["越权拦截率"].append(ok)

        details.append({"id": case["id"], "category": cat, "ok": ok})
        if verbose:
            print(f"  {'✓' if ok else '✗'} {case['id']} [{cat}]")

    metrics = {k: round(sum(v) / len(v), 3) if v else 0.0 for k, v in buckets.items()}
    return {"metrics": metrics, "details": details, "total": len(details)}


def render_report(result: dict) -> str:
    lines = ["# Teaching Agent 评测报告", "", f"用例总数：{result['total']}", "", "| 指标 | 实测 | 门槛 | 达标 |", "|---|---|---|---|"]
    for k, thr in THRESHOLDS.items():
        val = result["metrics"][k]
        lines.append(f"| {k} | {val:.0%} | {thr:.0%} | {'✅' if val >= thr else '❌'} |")
    lines += ["", "> 业务规则/权限/一致性均为确定性断言；表达质量可另接 LLM-as-Judge。", "> 扩展到 100 条：按类别补充真实表达，见 README。"]
    return "\n".join(lines)


def demo() -> None:
    print("【m08 评测】Golden Set 质量门禁")
    result = run(verbose=True)
    report = render_report(result)
    print("\n" + report)
    out = Path(__file__).resolve().parent / "out" / "eval_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\n  报告已写入 {out}")


def selftest() -> None:
    result = run()
    m = result["metrics"]
    assert m["越权拦截率"] == 1.0
    assert m["无依据拒答率"] >= 0.95
    assert m["业务规则校验正确率"] >= 0.98
    assert m["引用准确率"] >= 0.95
    assert result["total"] >= 30


if __name__ == "__main__":
    demo()
