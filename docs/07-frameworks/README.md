# 07 · 框架与 SDK

**目标**：知道框架替你做了什么、藏了什么，能按场景选型而不是跟风。

## 章节与状态

| 章节 | 状态 |
|---|---|
| （暂无成章，仅本页提纲） | ☐ |
| 规划：01-LangGraph vs CrewAI vs Harness 选型 | ☐ |
| 规划：02-框架抽象泄漏与迁移 | ☐ |

> 已成章的主题：02 / 05 / 11；全量清单见 [文档总索引](../INDEX.md)。

## 关注对象
- LangGraph（图/状态机）
- CrewAI（多角色协作）
- DeepSeek Harness（插件化 Agent 框架）
- OpenAI Agents SDK（handoff / guardrail / tracing）
- Claude Agent SDK（文件与工具驱动）
- LlamaIndex / AutoGen（按需了解）

## 已完成示例

### 1. 医疗教学 Agent 对照实现

[→ 查看代码](../../code/07-frameworks/medical-education/README.md)

同一个业务（内科住培教学活动设计）用两个框架各写一遍：
- **LangGraph**：状态图 + 条件边实现「评审不过就返工」
- **CrewAI**：4 个角色 + 4 个任务协作产出教案

特点：
- 离线 mock 模式，无需 API key 即可跑通
- 7B 小模型适配（硬约束、JSON 校验重试）
- 模型体检脚本（JSON 合规 / 指令边界 / 速度对比）
- 可视化 Web 界面（FastAPI + SSE + 原生前端）

### 2. DeepSeek Harness 扩展示例

[→ 查看代码](../../code/07-frameworks/harness-examples/README.md)

三种 DSH 插件开发方式：

| 示例 | 类型 | 说明 |
|------|------|------|
| review-preset | Agent Preset | 自定义只读代码审查 Agent（纯 YAML 配置） |
| medical-tool-plugin | Host Plugin | 为 Agent 添加医疗教学工具（JS 代码） |
| mcp-bundle-example | MCP Bundle | 连接外部 MCP 服务器（配置型） |

## 关键问题
- 状态怎么存？断点续跑怎么做？
- 可观测性（tracing）是内置的还是自己接？
- 换模型/换供应商的成本有多大？
- 出问题时，我能不能看到完整的 prompt 和工具调用？

## 产出
- [x] 用 LangGraph / CrewAI 重写阶段一的 mini agent
- [x] DeepSeek Harness 插件开发示例
- [ ] 对比表：抽象层级 / 状态管理 / 可观测 / 上手成本 / 我的评价
- [ ] 笔记：框架帮我省了什么，又让我更难调试什么
