# 05 · 规划与推理

**目标**：让 Agent 会把长任务拆开，并知道什么时候该反思、重试、放弃。

## 本章文档

> Demo 采用**医教领域**案例：组织一次「全院心肺复苏（CPR）技能考核」的多步骤任务。

- [01 · 模型做规划：Plan-and-Execute 与 ReAct](01-planning-with-models.md) —— 计划=步骤+依赖、两种范式取舍、按依赖执行，配可运行 demo。
- [02 · 计划校验与重规划](02-plan-validation-and-replan.md) —— 坏计划四类校验、局部重规划 vs 整体重来、反思边界、终止条件，配可运行 demo。

## 关键问题
- 先规划再执行（plan-and-execute）和边走边看（ReAct），各自什么时候更合适？
- 子任务怎么定义才算「可验证」？
- 反思（reflection）什么时候有用，什么时候只是浪费 token？
- 怎么防止计划越改越乱？

## 资料
- [ ] 待补充（plan-and-execute、reflexion 类工作、树搜索相关）

## 产出
- [ ] 一个多步骤任务（≥5 步）的分解实现
- [ ] 一次「反思有效 / 反思无效」的对比记录
- [ ] 笔记：我的 agent 什么时候开始原地打转，怎么检测到

## Teaching 场景落地（源文档 §6 Agent 与工作流编排）

配套可运行示例：[projects/teaching-agent/m05](../../projects/teaching-agent/m05_workflow.py)（LangGraph 替代 LangGraph4j）

基础概念：Agent / Tool / ReAct / Workflow / State / Graph / Checkpoint / HITL / Multi-Agent。

Teaching 首期活动创建流程（单 Agent + 显式工作流）：
```
用户输入 → 身份权限上下文 → 意图/字段抽取 → 缺项判断
   有缺项 → 澄清并等待补充(interrupt)
   无缺项 → 只读业务工具 → 生成草稿 DTO → 业务规则校验
         → 展示草稿 → 用户确认(HITL) → 既有业务 API 创建 → 返回结果
```

设计原则（m05 落地）：
1. 首期单 Agent + 显式工作流，不急于 Multi-Agent。
2. 工具白名单 + 参数/权限校验 + 调用次数限制。
3. 状态含任务 ID、用户/租户上下文、当前节点、草稿、错误。
4. 长任务状态持久化（SqliteSaver），不只依赖内存。
5. 人工确认绑定 用户/租户/草稿哈希/有效期/一次性凭证。
6. 最终写操作由原业务服务执行。
7. 工具调用设超时、重试边界、最大循环次数、Token 预算。

POC 验收：节点状态持久化、服务重启恢复、补充信息续跑、人工中断恢复、工具失败重试、任务取消与审计。
m05 的 start/resume CLI 跨进程演示了重启恢复与重放拒绝。
