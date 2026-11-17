# 01 · Agent 基础 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)
> 与 [code/07-frameworks/](../07-frameworks/README.md)，按「代码与 docs 同编号」约定在此索引，避免重复存放。

## 学什么

- LLM 能力边界：Token / 上下文窗口 / 采样参数。
- 结构化输出：让模型按 Schema 输出，**未经校验不得进入业务流程**。
- Agent 最小构成：模型 + 工具 + 上下文 + 循环 + 停止条件。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| 结构化输出 + DTO 校验 | [m01](../../projects/teaching-agent/m01_structured_output.py) | `cd projects/teaching-agent && ../../.venv/bin/python m01_structured_output.py` |
| 工作流基础（State/循环） | [m05](../../projects/teaching-agent/m05_workflow.py) | `../../.venv/bin/python m05_workflow.py` |
| 无框架手写循环对照 | [medical/langgraph](../07-frameworks/medical-education/langgraph_case_agent.py) | 见 [medical README](../07-frameworks/medical-education/README.md) |

## 对应笔记

→ [docs/01-foundations](../../docs/01-foundations/README.md)
