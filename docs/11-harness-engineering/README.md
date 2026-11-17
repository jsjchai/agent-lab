# 11 · Harness Engineering（ harness 工程）

> **质量试点主题**：本主题是 Agent Lab V2.0 文档质量的锚点，按「质量优先于数量」原则先行建设，
> 通过质量验收后再推广到其他主题。当前已完成 01/04/05/06/07/08 六章，其余（02/03/09/10/11）规划中。

## 学习目标

学完本主题，你应能：

1. 说清 **Harness / Agent / Framework** 三者的区别与关系，不再混用术语。
2. 理解 Harness 的核心职责：**把「会聊天的模型」变成「能可靠做事的系统」**。
3. 掌握 Agent Loop 的执行机制：step / turn / 上下文组装 / 工具流水线 / 停止条件。
4. 理解「会话日志即真相」的事件溯源设计，以及它如何支撑 fork / 恢复 / 回放。
5. 能动手写一个最小 Harness，并读懂真实 Harness（DeepSeek Harness）的架构。
6. 理解 Harness 的权限边界、错误恢复、长任务管理在生产中的意义。

## 前置知识

- 会 Python，理解函数/类/装饰器基本概念。
- 了解 LLM 对话与 Tool Calling 的基本流程（见 [01-foundations](../01-foundations/README.md)、[03-tool-use](../03-tool-use/README.md)）。
- 了解状态机/事件驱动的基本思想（见 [05-planning](../05-planning/README.md)）。
- 不要求事先了解 Cordis 或 DeepSeek Harness——本主题会从问题出发引入。

## 阅读顺序与章节地图

| 章 | 标题 | 核心问题 | 状态 |
|---|---|---|---|
| 01 | [ introduction：为什么需要 Harness](01-introduction.md) | 裸调模型差在哪？Harness 补什么？ | ✅ 已完成 |
| 02 | 核心概念：Harness/Agent/Framework/Loop | 术语边界与职责划分 | 🚧 规划中 |
| 03 | 架构：插件化与能力 seam | 为什么一切皆插件 | 🚧 规划中 |
| 04 | [执行循环：一次请求如何变成行动](04-execution-loop.md) | 取消/重试语义/事件持久化 | ✅ 已完成 |
| 05 | [上下文工程：模型看到什么](05-context-engineering.md) | 组装/压缩/注入 | ✅ 已完成 |
| 06 | [工具工程：受控流水线](06-tool-engineering.md) | 瀑布/单调守卫/fail-closed | ✅ 已完成 |
| 07 | [执行环境：Shell/文件/沙箱](07-execution-environment.md) | 能力seam/共享执行世界/围栏 | ✅ 已完成 |
| 08 | [错误恢复与 Checkpoint](08-error-recovery.md) | 悬空调用修复/重试vs恢复 | ✅ 已完成 |
| 09 | 权限与安全边界 | 审批/最小权限/注入防护 | 🚧 规划中 |
| 10 | 生产实践与 Harness 评测 | 长任务/可观测/对比 | 🚧 规划中 |
| 11 | 总结与知识关联 | 串联全主题 | 🚧 规划中 |

> 章节随质量验收逐个推进，不一次性铺薄提纲。

## 对应代码实验

| 实验 | 位置 | 验证什么 |
|---|---|---|
| 最小 Harness 骨架 | [code/11-harness-experiments/minimal_harness.py](../../code/11-harness-experiments/minimal_harness.py) | 事件日志即真相 / 工具白名单 / step-turn 循环 / 停止条件 |

运行：`cd code/11-harness-experiments && ../../.venv/bin/python minimal_harness.py`

## 对应工程项目

- [projects/teaching-agent](../../projects/teaching-agent/README.md)：m05 工作流是 Harness 思想在业务层的体现（State/Checkpoint/HITL）。
- [code/07-frameworks/harness-examples](../../code/07-frameworks/harness-examples/README.md)：真实 DeepSeek Harness 的插件扩展实践。

## 推荐学习路径

```
01-introduction（建立直觉）
  → 跑 minimal_harness.py（动手验证核心循环）
  → 04-execution-loop + 06-tool-engineering（深入机制）
  → 对照 teaching-agent/m05（看业务落地）
  → 07/08/09（生产化：环境/恢复/安全）
```

## 与其他主题的关系

- **上游**：01-foundations（模型能力）、03-tool-use（工具调用）是本主题的基础。
- **平行**：05-planning（工作流编排）与 Harness 的 Loop 互为表里。
- **下游**：12-coding-agent（Harness 在代码场景的应用）、14-agent-runtime（运行时机制）、15-agentops（运维评测）。

## 权威参考

- DeepSeek Harness 架构文档（本机安装版）：`architecture.zh.md`、`agent-lifecycle.zh.md`、`tool-execution-pipeline.zh.md`、`capability-seams.zh.md`
- [Cordis 框架](https://github.com/nicedoc/cordis)（DSH 底层插件框架）
- 本主题代码锚点：[minimal_harness.py](../../code/11-harness-experiments/minimal_harness.py)
