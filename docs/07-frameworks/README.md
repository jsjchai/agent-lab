# 07 · 框架与 SDK

**目标**：知道框架替你做了什么、藏了什么，能按场景选型而不是跟风。

## 关注对象
- LangGraph（图/状态机）
- OpenAI Agents SDK（handoff / guardrail / tracing）
- Claude Agent SDK（文件与工具驱动）
- LlamaIndex / CrewAI / AutoGen（按需了解）

## 已完成示例

- [医疗教学 Agent 对照实现](../../code/07-frameworks/medical-education/README.md)
  同一个业务（内科住培教学活动设计）用两个框架各写一遍：
  LangGraph 用状态图 + 条件边实现「评审不过就返工」，CrewAI 用 4 个角色 + 4 个任务协作产出教案。
  两者都带离线 mock 模式，无需 API key 即可跑通并测试。

## 关键问题
- 状态怎么存？断点续跑怎么做？
- 可观测性（tracing）是内置的还是自己接？
- 换模型/换供应商的成本有多大？
- 出问题时，我能不能看到完整的 prompt 和工具调用？

## 产出
- [ ] 用其中 1~2 个重写阶段一的 mini agent
- [ ] 对比表：抽象层级 / 状态管理 / 可观测 / 上手成本 / 我的评价
- [ ] 笔记：框架帮我省了什么，又让我更难调试什么
