# 03 · 工具调用

**目标**：不靠框架，亲手跑通一次完整的「模型决定调工具 → 执行 → 回填 → 继续」。

## 关键问题
- 模型是**怎么**决定调哪个工具、传什么参数的？（看 schema，还是看自然语言描述？）
- 工具描述写不好会怎样？参数该由谁校验？
- 工具报错、超时、参数非法时，循环怎么继续？
- MCP 解决了什么问题？什么时候值得上？

## 资料
- [ ] 待补充（Function Calling 官方文档、MCP 规范）

## 产出
- [ ] 手写 function calling 循环（schema → 决策 → 执行 → 回填 → 终止）
- [ ] 同一工具，对比「好描述」和「坏描述」的调用成功率
- [ ] 一个必须多轮修正才能完成的工具任务（如查天气后决定带不带伞）

## Teaching 场景落地（源文档 §7 Tool Calling 与业务工具设计）

配套可运行示例：[projects/teaching-agent/m04](../../projects/teaching-agent/m04_tools.py)

P0 工具白名单（只读 / 校验 / 纯计算，**不开放写工具**）：
`queryActivityRules`、`queryRotationSnapshot`、`queryOrgScope`、`searchParticipants`、
`validateActivityDraft`、`searchTeachingKnowledge`、`buildActivityDraft`。

每个工具须定义：用途、版本、输入 Schema、权限上下文、超时、最大调用次数、返回 DTO、错误码、审计字段、幂等策略。

安全规则（m04 逐条落地为断言）：
- 每次调用重新校验身份和权限。
- **不信任模型提供的 userId / tenantId / orgId**。
- 不允许模型任意拼接 URL / SQL / 命令。
- P0 不开放发布 / 审批 / 删除等写工具。
- 工具只返回完成任务所需的最小数据。

验收：越权调用被拒绝、非法参数被拦截、调用有审计、工具故障不导致无限循环。
