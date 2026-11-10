# 07 · 框架与 SDK

**目标**：知道框架替你做了什么、藏了什么，能按场景选型而不是跟风。

## 关注对象
- LangGraph（图/状态机）
- OpenAI Agents SDK（handoff / guardrail / tracing）
- Claude Agent SDK（文件与工具驱动）
- LlamaIndex / CrewAI / AutoGen（按需了解）

## 关键问题
- 状态怎么存？断点续跑怎么做？
- 可观测性（tracing）是内置的还是自己接？
- 换模型/换供应商的成本有多大？
- 出问题时，我能不能看到完整的 prompt 和工具调用？

## 产出
- [ ] 用其中 1~2 个重写阶段一的 mini agent
- [ ] 对比表：抽象层级 / 状态管理 / 可观测 / 上手成本 / 我的评价
- [ ] 笔记：框架帮我省了什么，又让我更难调试什么
