# 01 · Agent 基础

**目标**：说清 Agent 是什么、能做什么、什么时候**不该**用 Agent。

## 章节与状态

| 章节 | 状态 |
|---|---|
| （暂无成章，仅本页提纲） | ☐ |
| 规划：01-ReAct 循环与 Agent 边界 | ☐ |
| 规划：02-Agent vs Workflow：何时用哪种 | ☐ |

> 已成章的主题：02 / 05 / 11；全量清单见 [文档总索引](../INDEX.md)。

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

## Teaching 场景落地（源文档 §3 LLM 基础）

配套可运行示例：[projects/teaching-agent/m01](../../projects/teaching-agent/m01_structured_output.py)、[m05](../../projects/teaching-agent/m05_workflow.py)

必须掌握的概念：
- **Token / Context Window**：文本切分与计量，决定费用和上下文上限。
- **Temperature / Top-p**：控制生成随机性；结构化抽取用低温（0）。
- **Embedding**：文本→向量，用于语义检索（见 04）。
- **Tool Calling**：模型提出调用请求，由应用执行并回传结果（见 03）。
- **Structured Output**：按 Schema/DTO 约束输出，**未经校验不得进入业务流程**。
- **多轮对话**：历史消息、摘要、窗口裁剪、状态管理。

验收：输出可稳定解析；字段缺失/类型错误/非法枚举能被程序拦截。
m01 用 pydantic DTO 把这些拦截变成断言（替代 Spring AI + Bean Validation）。
