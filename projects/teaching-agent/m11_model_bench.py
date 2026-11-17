#!/usr/bin/env python3
"""m11 · 模型横向对比基准 —— 对应文档 §9 模型路由/选型 + §12 评测。

对多个模型（mock 基线 / qwen2.5:7b / qwen3:8b）跑同一组任务，量化：
- 意图抽取准确率（槽位 + 缺项是否符合 ground truth）
- 槽位漂移次数（原始输出 vs 归一化后不一致 => 小模型格式漂移，需代码兜底）
- JSON 校验重试次数
- 平均延迟
- RAG 引用准确率 / 无依据拒答率

结果写入 out/model_bench.json，供可视化「评测与安全」面板展示。

运行（真实模型需 Ollama）：
    ../../.venv/bin/python m11_model_bench.py                       # 默认 mock + 7b + 8b
    ../../.venv/bin/python m11_model_bench.py --models mock qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import m02_intent_slots as m02
import m06_rag as m06
from common.llm import LLM, mock_extract_intent
from common.security import authenticate

OLLAMA_BASE = "http://localhost:11434/v1"

# (输入, 期望槽位子集, 期望缺项；None 表示问答题只查 intent)
INTENT_CASES = [
    ("创建11月20日的数学教研活动，面向三年级教师，主讲人：张三、李四",
     {"activity_type": "教研活动", "subject": "数学", "date_text": "11月20日", "speakers": ["张三", "李四"]}, []),
    ("帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人",
     {"subject": "数学", "activity_type": "教研活动"}, ["date_text", "speakers"]),
    ("组织明天下午的语文培训，面向全体教师，主讲人：王五",
     {"subject": "语文", "date_text": "明天", "speakers": ["王五"]}, []),
    ("创建三年级英语公开课，11月25日，面向三年级教师，主讲人：赵六",
     {"subject": "英语", "date_text": "11月25日", "speakers": ["赵六"]}, []),
    ("帮我安排一个教研活动", {"activity_type": "教研活动"}, ["subject", "date_text", "audience", "speakers"]),
    ("创建六年级语文教研活动，11月28日，面向六年级教师，主讲人：林静、周涛",
     {"subject": "语文", "grade": "六年级", "date_text": "11月28日", "speakers": ["林静", "周涛"]}, []),
    ("什么是教研活动？", {}, None),
    ("创建数学教研活动，11月20日，面向三年级教师", {"subject": "数学", "date_text": "11月20日"}, ["speakers"]),
]

# (问题, 用户, 是否可答)
RAG_CASES = [
    ("活动时长有什么规定？", "u1", True),
    ("如何查询轮转计划？", "u1", True),
    ("文档入库的流程是什么？", "u3", True),
    ("量子力学的基本原理是什么？", "u1", False),
    ("今天食堂吃什么？", "u1", False),
]


def make_llm(model: str) -> LLM:
    if model == "mock":
        return LLM("mock")
    return LLM("openai", model=model, base_url=OLLAMA_BASE, api_key="ollama", embed_model="bge-m3")


def bench_intent(llm: LLM) -> dict:
    correct, drift, retries, latencies = 0, 0, 0, []
    for text, want_slots, want_missing in INTENT_CASES:
        err_before = llm.stats["errors"]
        t0 = time.time()
        raw = llm.chat_json(m02.build_messages(text), validate=m02._validate_intent, retries=2)
        if "_error" in raw:
            norm = mock_extract_intent(text)
            drift += 1
        else:
            norm = m02._normalize(raw, text)
            if raw.get("slots") != norm["slots"] or set(raw.get("missingFields", [])) != set(norm["missingFields"]):
                drift += 1
        latencies.append(time.time() - t0)
        retries += llm.stats["errors"] - err_before

        if want_missing is None:
            ok = norm.get("intent") == "knowledge_qa"
        else:
            slots_ok = all(norm["slots"].get(k) == v for k, v in want_slots.items())
            missing_ok = set(norm["missingFields"]) == set(want_missing)
            ok = slots_ok and missing_ok
        correct += ok
    n = len(INTENT_CASES)
    return {
        "accuracy": round(correct / n, 3),
        "drift_cases": drift,
        "json_retries": retries,
        "avg_latency_s": round(sum(latencies) / n, 2),
        "cases": n,
    }


def bench_rag(llm: LLM) -> dict:
    index = m06.KnowledgeIndex(llm)
    index.build()
    cite_ok, answerable, refuse_ok, refusals, latencies = 0, 0, 0, 0, []
    for query, user, answerable_q in RAG_CASES:
        ctx = authenticate(user)
        t0 = time.time()
        ans = index.answer(ctx, query)
        latencies.append(time.time() - t0)
        if answerable_q:
            answerable += 1
            cite_ok += bool(ans.get("citations")) and set(ans["citations"]).issubset(set(ans.get("retrieved", [])))
        else:
            refusals += 1
            refuse_ok += (not ans.get("citations"))
    return {
        "citation_accuracy": round(cite_ok / max(answerable, 1), 3),
        "refusal_accuracy": round(refuse_ok / max(refusals, 1), 3),
        "avg_latency_s": round(sum(latencies) / len(RAG_CASES), 2),
    }


def run(models: list[str]) -> dict:
    rows = []
    for model in models:
        print(f"  ⏳ {model} ...", flush=True)
        llm = make_llm(model)
        try:
            intent = bench_intent(llm)
            rag = bench_rag(llm)
            rows.append({"model": model, "intent": intent, "rag": rag, "error": None})
            print(f"     意图准确率 {intent['accuracy']:.0%} 漂移 {intent['drift_cases']} "
                  f"重试 {intent['json_retries']} | RAG 引用 {rag['citation_accuracy']:.0%} 拒答 {rag['refusal_accuracy']:.0%}")
        except Exception as exc:
            rows.append({"model": model, "intent": None, "rag": None, "error": str(exc)[:120]})
            print(f"     ✗ 失败：{exc}")
    return {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "models": rows}


def selftest() -> None:
    """mock 基线快速自检（真实模型对比请用 CLI 运行，耗时较长）。"""
    llm = make_llm("mock")
    intent = bench_intent(llm)
    rag = bench_rag(llm)
    assert intent["accuracy"] == 1.0 and intent["drift_cases"] == 0
    assert rag["citation_accuracy"] == 1.0 and rag["refusal_accuracy"] == 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["mock", "qwen2.5:7b", "qwen3:8b"])
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "out" / "model_bench.json"))
    args = parser.parse_args()

    print("【m11 模型横向对比】")
    result = run(args.models)
    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
