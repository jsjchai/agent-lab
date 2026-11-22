# 02 · 提示与上下文工程

**目标**：让模型输出**稳定、可解析、可测试**，而不是「偶尔很惊艳」。

## 本章文档

> 本章三个 demo 采用**医教领域**案例：临床教学管理助手（教学查房 / 病例讨论 / 技能培训 / 住院医师规培）。

- [01 · 意图识别：Agent 的第一道门](01-intent-recognition.md) —— 医教意图/槽位/多意图/置信度、三种分类器取舍、归一化、**调接口 vs 问答路由**，配可运行 demo。
- [02 · 接口有 40 个参数怎么办](02-api-param-strategy.md) —— 医教「创建教学活动」40 参接口：参数六层分层（system/core/derived/default/conditional/form）、40→5 换算、草稿优先，配可运行 demo。
- [03 · Agent 的意图路由怎么设计](03-agent-intent-routing.md) —— 路由表 / 候选打分 / 阈值+边距 / 三态出口 / 风险分级 / 子代理分发，配可运行 demo。

## 关键问题
- 同一个任务，为什么换一种上下文组织方式效果差很多？
- 结构化输出（JSON / schema）怎么保证不崩？崩了怎么兜底？
- 上下文里哪些该给、哪些该藏？token 预算怎么分配？

## 资料
- [ ] 待补充（各家 prompting 指南、结构化输出文档）

## 产出
- [ ] 一个输出稳定 JSON 的 prompt（跑 20 次不崩）
- [ ] 一个「少样本 vs 零样本」的对比实验记录
- [ ] 笔记：我踩过的格式漂移 / 幻觉 / 指令冲突

## 业务落地参考（teaching-agent 项目，学校教研场景）

> 说明：本章上面的两个 demo 是**医教场景**；这里链接的是仓库另一个完整项目 `teaching-agent`（学校教研场景），
> 两者是同构的「意图 → 槽位 → 结构化输出」实现，可对照阅读。

配套可运行示例：[projects/teaching-agent/m02](../../projects/teaching-agent/m02_intent_slots.py)

核心知识：
- System / Developer / User Prompt 的职责边界。
- Prompt Template、变量注入、Few-shot。
- **Context Engineering**：选择、压缩、排序、组织上下文。
- 对话历史管理：完整历史 / 摘要 / 窗口裁剪。
- **Prompt 版本管理**：版本号 + 变更记录 + 回归测试（m02 的 `PROMPT_VERSION`）。
- **Prompt Injection**：用户输入或检索文档试图改变系统指令（见 09）。
- 输出约束：JSON Schema、枚举、长度、拒答条件。

Teaching 实战：面对「帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人」，
输出 `intent / slots / missingFields / questions`，判断缺项、决定哪些可查哪些须澄清，
生成草稿而非直接创建。m02 用 21 条真实表达做回归。

医教框架参考：[code/07-frameworks/medical-education](../../code/07-frameworks/medical-education/README.md)（LangGraph + CrewAI 医教示例）。

验收：Prompt 变更触发回归；用户输入和检索文档不能覆盖系统安全规则。
