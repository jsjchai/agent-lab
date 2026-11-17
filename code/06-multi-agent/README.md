# 06 · 多智能体 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [code/07-frameworks/](../07-frameworks/README.md)。
> 教学场景首期遵循文档建议「单 Agent + 显式工作流，不急于 Multi-Agent」，
> 多角色协作的对照实现见医疗示例。

## 学什么

- 什么时候多智能体真的比单智能体好（职责分工清晰、产出可流水线串联）。
- 角色人设（role/goal/backstory）+ 任务上下文传递（`context=`）。
- 顺序编排 vs 图式编排的取舍；多智能体的调试成本。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| CrewAI 4 角色协作产教案 | [crewai_teaching_activity](../07-frameworks/medical-education/crewai_teaching_activity.py) | `cd code/07-frameworks/medical-education && AGENT_LLM=mock ../../../.venv/bin/python crewai_teaching_activity.py` |
| LangGraph vs CrewAI 对照 | [medical README](../07-frameworks/medical-education/README.md) | 见 README |
| DSH 子代理 / 团队编排 | [harness-examples](../07-frameworks/harness-examples/README.md) | 见 README |

## 对应笔记

→ [docs/06-multi-agent](../../docs/06-multi-agent/README.md)
