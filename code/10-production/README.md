# 10 · 工程化与上线 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)。

## 学什么

- 模型路由：任务类型 / 合规 / 成本 / 延迟 / 熔断；**PRIVATE_ONLY 不回退云端**。
- 异步任务可靠性：Outbox / 幂等键 / 租约心跳 / 指数退避 / 死信转人工 / 取消边界。
- 成本与延迟：单任务 Token / 费用 / P50/P95；超时重试不重复副作用。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| 模型路由 + 合规回退 + 熔断 | [m09](../../projects/teaching-agent/m09_router.py) | `cd projects/teaching-agent && ../../.venv/bin/python m09_router.py` |
| Outbox/幂等/租约/重试（SQLite） | [m10](../../projects/teaching-agent/m10_reliability.py) | `../../.venv/bin/python m10_reliability.py` |
| 模型延迟/成本对比 | [m11](../../projects/teaching-agent/m11_model_bench.py) | `../../.venv/bin/python m11_model_bench.py` |

## 对应笔记

→ [docs/10-production](../../docs/10-production/README.md)
