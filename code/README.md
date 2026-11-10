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
| `02-prompt-context/` | 结构化输出、上下文组织对比 |
| `03-tool-use/` | function calling 循环、工具描述对比、MCP 试验 |
| `04-memory-rag/` | 切块/检索/记忆读写的最小实现 |
| `05-planning/` | 任务分解、反思、重试 |
| `06-multi-agent/` | 角色编排与通信 |
| `07-frameworks/` | 同题重写：LangGraph / 官方 SDK |
| `08-eval-observability/` | 评测脚本、打分器、trace 解析 |
| `09-safety-guardrails/` | 注入样本、拦截层 |
| `10-production/` | 缓存、并行、超时重试、成本统计 |
| `_shared/` | 公共工具 |
