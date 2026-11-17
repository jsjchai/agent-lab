# 08 · 评测与可观测 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)。

## 学什么

- Golden Set + **确定性断言**（业务规则/权限/一致性不靠 LLM-as-Judge）。
- 指标门槛：任务成功率 / 字段完整率 / 校验正确率 / 引用准确率 / 拒答率 / 越权拦截率。
- 模型横向对比：准确率 / 槽位漂移 / JSON 重试 / 延迟。
- 可观测：TraceId / Token / 耗时 / 工具调用 / 错误码 / 重试次数。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| Golden Set 评测门禁 | [m08](../../projects/teaching-agent/m08_eval.py) | `cd projects/teaching-agent && ../../.venv/bin/python m08_eval.py` |
| 模型横向对比基准 | [m11](../../projects/teaching-agent/m11_model_bench.py) | `../../.venv/bin/python m11_model_bench.py` |
| 评测种子集（30 条） | [golden_set.jsonl](../../projects/teaching-agent/golden_set.jsonl) | 扩展到 100 条见项目 README |

## 对应笔记

→ [docs/08-eval-observability](../../docs/08-eval-observability/README.md)
