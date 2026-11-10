#!/usr/bin/env python3
"""小模型体检：用同一组任务横向对比不同模型，别靠感觉选模型。

它只测三件在真实 Agent 里最容易翻车、又跟模型规模强相关的事：

    1. 结构化输出   —— 能不能稳定吐出可解析、自洽的 JSON（评审节点依赖它）
    2. 指令边界     —— 让它设计"90 分钟教学"，会不会写成"4 周课程"
    3. 速度与啰嗦   —— 单次耗时、输出字数（直接决定成本和迭代效率）

用法：

    # 先确认 ollama 在跑
    AGENT_LLM=openai OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \
      ../../../.venv/bin/python bench_models.py --models qwen2.5:7b qwen3:8b --runs 2

    # 对比官方接口
    AGENT_LLM=openai OPENAI_API_KEY=sk-... \
      ../../../.venv/bin/python bench_models.py --models gpt-4o-mini gpt-4o --runs 2
"""

from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.llm import LLMClient, extract_json  # noqa: E402

REVIEW_SYSTEM = (
    "你是严格的教学督导。只输出 JSON："
    '{"score": int, "verdict": "pass"|"needs_revision", "issues": [str], "suggestion": str}'
)
REVIEW_USER = """教学主题：社区获得性肺炎（CAP）
教学目标：3 条（知识/技能/素养）
教学病例：65 岁男性，发热咳嗽 5 天，右下肺湿啰音，胸片示右下肺浸润影
分层问题：3 道（记忆/应用/分析）

请评审。特别注意：分数与 verdict 必须自洽——有 issues 就不能是 pass。"""

PLAN_SYSTEM = "你是三甲医院内科的教学设计师，只输出教学目标与安排，不要寒暄。"
PLAN_USER = """教学主题：社区获得性肺炎（CAP）
学习者：住院医师规范化培训第一年（R1）
请设计教学目标，并给出时长分配。
硬约束：这是一次 90 分钟的教学活动，不要写成多周课程。"""


def check_review(raw: str) -> tuple[bool, str]:
    """返回 (是否合格, 不合格原因)。合格 = 字段齐全、类型正确、分数与结论自洽。"""
    data = extract_json(raw)
    if not isinstance(data, dict) or "score" not in data:
        return False, "非 JSON / 缺 score"
    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        return False, "score 不是 0-100 整数"
    if data.get("verdict") not in {"pass", "needs_revision"}:
        return False, "verdict 非法"
    if not isinstance(data.get("issues"), list):
        return False, "issues 不是数组"
    # 自洽性：有 issues 却判 pass，或没 issues 却判 needs_revision
    if data["issues"] and data["verdict"] == "pass":
        return False, "有 issues 却判 pass"
    return True, ""


def check_scale(raw: str) -> tuple[bool, str]:
    """检查是否守住了「一次 90 分钟教学」的边界。

    不能只认字面上的 "90"：写成「前 15 分钟 / 中间 45 分钟 / 后 30 分钟」也是合规的。
    真正要抓的是"跑偏成多周课程"这种规模错误。
    """
    has_week = bool(re.search(r"\d+\s*周|第[一二三四五六七八九十]+周|[一二三四]\s*周", raw))
    if has_week:
        return False, "跑偏成多周课程"
    minute_marks = re.findall(r"\d+\s*分钟", raw)
    if len(minute_marks) < 2:
        return False, "缺少分钟级时间分配"
    return True, ""


def run_model(model: str, runs: int) -> dict:
    os.environ["AGENT_MODEL"] = model
    client = LLMClient("openai")

    review_ok, review_reason = 0, []
    plan_ok, plan_reason = 0, []
    latencies: list[float] = []
    chars: list[int] = []

    for i in range(runs):
        t0 = time.perf_counter()
        raw = client.complete("review", REVIEW_SYSTEM, REVIEW_USER, temperature=0.0)
        latencies.append(time.perf_counter() - t0)
        chars.append(len(raw))
        ok, why = check_review(raw)
        review_ok += ok
        if not ok:
            review_reason.append(why)

        t0 = time.perf_counter()
        raw = client.complete("plan", PLAN_SYSTEM, PLAN_USER, temperature=0.0)
        latencies.append(time.perf_counter() - t0)
        chars.append(len(raw))
        ok, why = check_scale(raw)
        plan_ok += ok
        if not ok:
            plan_reason.append(why)

    return {
        "model": model,
        "review": f"{review_ok}/{runs}",
        "scale": f"{plan_ok}/{runs}",
        "latency": statistics.mean(latencies),
        "chars": statistics.mean(chars),
        "review_reason": "；".join(sorted(set(review_reason))) or "-",
        "scale_reason": "；".join(sorted(set(plan_reason))) or "-",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="小模型体检：JSON 合规 / 指令边界 / 速度")
    parser.add_argument("--models", nargs="+", required=True, help="要对比的模型名，如 qwen2.5:7b gpt-4o-mini")
    parser.add_argument("--runs", type=int, default=2, help="每个模型跑几轮（建议 2-3）")
    args = parser.parse_args()

    print(f"【模型体检】base_url={os.getenv('OPENAI_BASE_URL') or 'https://api.openai.com/v1'}，每个模型 {args.runs} 轮\n")
    rows = []
    for model in args.models:
        print(f"  ⏳ {model} ...", flush=True)
        try:
            rows.append(run_model(model, args.runs))
        except Exception as exc:  # 单个模型失败不影响其他模型
            rows.append(
                {
                    "model": model,
                    "review": "ERR",
                    "scale": "ERR",
                    "latency": 0.0,
                    "chars": 0,
                    "review_reason": str(exc)[:60],
                    "scale_reason": "-",
                }
            )

    print("\n| 模型 | JSON 合规 | 守住 90 分钟 | 平均耗时 | 平均字数 | 失败原因 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        reason = " / ".join(x for x in (r["review_reason"], r["scale_reason"]) if x != "-") or "-"
        print(
            f"| `{r['model']}` | {r['review']} | {r['scale']} | "
            f"{r['latency']:.1f}s | {r['chars']:.0f} | {reason} |"
        )
    print("\n解读：JSON 合规率决定评审节点能不能用；守住 90 分钟决定指令跟随；")
    print("耗时/字数决定迭代成本。小模型通常在前两项掉分，于是需要额外的校验与重试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
