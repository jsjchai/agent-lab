# 07 · 框架与 SDK — 代码索引

本目录含两组**完整框架对照实现**，是仓库里最重的代码块。按「代码与 docs 同编号」约定，
其余主题（01-06、08-10）的最小示例索引在各自目录的 README，实际代码多复用这里的公共层与
[projects/teaching-agent/](../../projects/teaching-agent/README.md)。

## 子项目

| 子项目 | 说明 | 入口 |
|---|---|---|
| [medical-education](medical-education/README.md) | 同一医疗教学业务用 **LangGraph vs CrewAI** 各写一遍 + 可视化界面 + 小模型适配 + 模型体检 | `langgraph_case_agent.py` / `crewai_teaching_activity.py` / `webui/server.py` |
| [harness-examples](harness-examples/README.md) | **DeepSeek Harness** 插件开发三种方式：Agent Preset / Host Plugin / MCP Bundle | 各子目录 `cordis.patch.yml` |

## 快速运行

```bash
# 医疗教学（离线 mock）
cd medical-education
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py
../../../.venv/bin/python webui/server.py        # http://127.0.0.1:7861

# Harness 插件：通过 DSH Web GUI → Plugins → Add plugin 选择子目录
```

## 对应笔记

→ [docs/07-frameworks](../../docs/07-frameworks/README.md)
