# 代码

与 `docs/` 同编号：`code/03-tool-use/` 对应 [docs/03-tool-use/](../docs/03-tool-use/)。

## 约定

- 一个文件 = 一个可运行的最小示例，命名 `NN_做什么.py`（如 `01_react_loop.py`）。
- 文件顶部写清三件事：**目的 / 运行方式 / 依赖**。
- 公共代码放 `_shared/`（LLM client、重试、日志、env 加载），不要复制粘贴。
- 依赖按需装，用到的库版本记在对应主题目录的 `requirements.txt`（需要时才建）。
- 不提交 API key：从 `.env` 读，模板见 [.env.example](../.env.example)。
- 示例要能**单独跑**；跑不通就不算完成，放在 `notebooks/` 继续折腾。

## 目录

| 目录 | 内容 |
|---|---|
| `01-foundations/` | 无框架手写 ReAct 循环、停止条件实验 |
| `02-prompt-context/` | 6 个 demo：意图识别、40 参分层、意图路由、置信度校准、小模型优化、JEV 模拟 |
| `03-tool-use/` | function calling 循环、工具描述对比、MCP 试验 |
| `04-memory-rag/` | 切块/检索/记忆读写的最小实现 |
| `05-planning/` | 规划范式 / 校验与重规划（1 个 demo） |
| `06-multi-agent/` | 角色编排与通信 |
| `07-frameworks/` | 框架对照实现 |
| ├─ `medical-education/` | LangGraph vs CrewAI + 可视化界面 + 小模型适配 |
| └─ `harness-examples/` | DeepSeek Harness 插件开发（Preset / Host Plugin / MCP） |
| `08-eval-observability/` | 评测脚本、打分器、trace 解析 |
| `09-safety-guardrails/` | 注入样本、拦截层 |
| `10-production/` | 缓存、并行、超时重试、成本统计 |
| `_shared/` | 公共工具 |

## 已完成示例

### 02-prompt-context（6 个）

```bash
cd code/02-prompt-context
../../.venv/bin/python intent_recognition.py      # 意图识别（规则 vs LLM + 归一化 + 路由）
../../.venv/bin/python large_api_params.py        # 40 参接口分层
../../.venv/bin/python intent_router.py           # 路由设计（打分/阈值/兜底）
../../.venv/bin/python confidence_calibration.py  # 置信度校准（ECE/温度缩放）
../../.venv/bin/python small_model_optimization.py# 小模型优化阶梯
../../.venv/bin/python jev_decision_demo.py       # JEV 决策接口模拟（不联网）
```

### 05-planning（1 个）

```bash
cd code/05-planning && ../../.venv/bin/python planning_demo.py
```

### 11-harness-experiments（7 个）

```bash
cd code/11-harness-experiments
for f in minimal_harness execution_loop tool_pipeline context_window sandbox_env checkpoint_recovery injection_defense; do
  ../../.venv/bin/python "$f.py"
done
```

### 07-frameworks/medical-education

医疗教学 Agent 对照实现，包含：
- `langgraph_case_agent.py` - LangGraph 状态机 + 评审回环
- `crewai_teaching_activity.py` - CrewAI 多角色协作
- `webui/` - FastAPI + SSE 可视化界面
- `bench_models.py` - 模型体检脚本
- `common/llm.py` - 统一 LLM 适配层（mock / openai / 小模型档位）

运行：
```bash
cd code/07-frameworks/medical-education
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py
../../../.venv/bin/python webui/server.py  # 启动 Web 界面
```

### 07-frameworks/harness-examples

DeepSeek Harness 插件开发示例：
- `review-preset/` - Agent Preset（纯 YAML 配置）
- `medical-tool-plugin/` - Host Plugin（JS 代码注册工具）
- `mcp-bundle-example/` - MCP Bundle（连接外部 MCP 服务器）

安装：通过 DSH Web GUI → Plugins → Add plugin 选择对应目录。
