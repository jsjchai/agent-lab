# 02 · 提示与上下文工程 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)，
> 按「代码与 docs 同编号」约定在此索引。

## 学什么

- System / User Prompt 职责边界；Prompt Template 与 Few-shot。
- 意图识别 + 槽位抽取 + 缺项澄清（`intent / slots / missingFields / questions`）。
- **Prompt 版本管理**：版本号 + 变更记录 + 回归测试。
- 结构化输出的 schema 约束与确定性归一化（小模型漂移兜底）。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| **意图识别独立 demo**（规则 vs LLM + 归一化 + 路由 + 评测） | [intent_recognition.py](intent_recognition.py) | `cd code/02-prompt-context && ../../.venv/bin/python intent_recognition.py` |
| **40 参接口分层 demo**（system/core/derived/default/conditional/form） | [large_api_params.py](large_api_params.py) | `../../.venv/bin/python large_api_params.py` |
| 意图/槽位/澄清 + 21 条回归 | [m02](../../projects/teaching-agent/m02_intent_slots.py) | `cd projects/teaching-agent && ../../.venv/bin/python m02_intent_slots.py` |
| 模型横向对比（prompt 效果） | [m11](../../projects/teaching-agent/m11_model_bench.py) | `../../.venv/bin/python m11_model_bench.py` |

## 对应笔记

→ [docs/02-prompt-context](../../docs/02-prompt-context/README.md) ·
[意图识别教材](../../docs/02-prompt-context/01-intent-recognition.md) · [40参策略](../../docs/02-prompt-context/02-api-param-strategy.md)
