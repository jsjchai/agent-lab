# 05 · 规划与工作流 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)
> 与 [code/07-frameworks/medical-education/](../07-frameworks/medical-education/README.md)。

## 学什么

- Agent / Workflow / ReAct 的边界；单 Agent + 显式工作流优先。
- State / Graph / 条件边 / **Checkpoint 持久化** / interrupt 恢复。
- **HITL**：关键步骤人工确认，凭证绑定用户/租户/草稿哈希/有效期/一次性。
- 最大循环次数 + 超时，防止无限规划。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| LangGraph 工作流 + Checkpoint + HITL | [m05](../../projects/teaching-agent/m05_workflow.py) | `cd projects/teaching-agent && ../../.venv/bin/python m05_workflow.py` |
| 评审回环对照（LangGraph） | [langgraph_case_agent](../07-frameworks/medical-education/langgraph_case_agent.py) | 见 [medical README](../07-frameworks/medical-education/README.md) |
| 交互式可视化（澄清/确认） | [webui](../../projects/teaching-agent/webui/server.py) | `../../.venv/bin/python webui/server.py` |

## 对应笔记

→ [docs/05-planning](../../docs/05-planning/README.md)
