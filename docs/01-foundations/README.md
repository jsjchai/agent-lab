# 01 · Agent 基础

**目标**：说清 Agent 是什么、能做什么、什么时候**不该**用 Agent。

## 关键问题
- 单次 LLM 调用 / Workflow（固定流程）/ Agent（自主决策）三者的边界在哪？
- ReAct 的 Thought → Action → Observation 循环，什么时候该停？
- 一个 Agent 的最小构成：模型 + 工具 + 上下文 + 循环 + 停止条件。

## 资料
- [ ] 待补充（框架官方「什么是 agent」文档、经典博客）

## 产出
- [ ] 30 行以内的手写 ReAct 循环（无框架）→ `code/01-foundations/`
- [ ] 一页笔记：什么任务用 Workflow，什么任务才值得上 Agent
- [ ] 一次失败复盘：无限循环 / 工具乱调 / 提前停止，各记一个例子
