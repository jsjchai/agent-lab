# agent-lab

Agent 学习与实践仓库：**资料在 `docs/`，小步实验代码在 `code/`，完整项目在 `projects/`。**

默认面向 LLM Agent（工具调用 / 检索 / 多智能体 / 评测）。如果以后要加强化学习 Agent，也放进对应的 `01-10` 主题或 `projects/`，结构不用改。

## 🗺️ 内容地图（先看这里）

实际代码集中在三块，`code/01-10` 各目录是**主题导航页**（索引到下面的真实示例，不重复存代码）：

| 内容块 | 位置 | 是什么 |
|---|---|---|
| **Teaching Agent 知识体系** | [projects/teaching-agent/](projects/teaching-agent/README.md) | 源文档 10 大模块的 Python 落地（m01–m11）+ 可交互可视化 + 评测门禁 + 模型对比，`run_all.py` 一键验收 11/11 |
| **框架对照实现** | [code/07-frameworks/](code/07-frameworks/README.md) | 医疗教学 LangGraph vs CrewAI（含可视化/小模型适配）+ DeepSeek Harness 插件三式 |
| **主题笔记** | [docs/](docs/README.md) | 01–11 知识点（02/05/11 已成章，共 18 篇）+ 路线图 + 论文索引 + 学习日志；全量清单见 [docs/INDEX.md](docs/INDEX.md) |

**怎么开始**：想系统学 → 读 [docs/00-roadmap.md](docs/00-roadmap.md)；想直接跑 → 下面「快速开始」；
想按主题找代码 → 进 `code/0X/README.md` 导航页。

## ✅ 已完成内容

| 模块 | 说明 | 状态 |
|------|------|------|
| [Teaching Agent 知识体系](projects/teaching-agent/) | 源文档 10 大模块的 Python 落地（m01–m11），离线可跑，run_all 验收 11/11 | ☑ 完成 |
| [医疗教学 Agent](code/07-frameworks/medical-education/) | LangGraph vs CrewAI 对照实现，含可视化界面 | ☑ 完成 |
| [Harness 扩展示例](code/07-frameworks/harness-examples/) | DeepSeek Harness 插件开发：Preset / Host Plugin / MCP Bundle | ☑ 完成 |
| [小模型适配](code/07-frameworks/medical-education/README.md#小模型本地-7b8b怎么跑) | 7B/8B 本地模型适配、硬约束、JSON 校验重试 | ☑ 完成 |
| [模型体检脚本](code/07-frameworks/medical-education/bench_models.py) | JSON 合规 / 指令边界 / 速度对比 | ☑ 完成 |

## 目录一览

```
agent-lab/
├── docs/            # 学习资料：路线图、主题笔记、论文、日志
├── code/            # 主题导航：01-10 各目录 README 索引到真实示例
│   └── 07-frameworks/         # 实际代码块：框架对照实现
│       ├── medical-education/   # LangGraph vs CrewAI + 可视化界面
│       └── harness-examples/    # DeepSeek Harness 插件开发示例
├── notebooks/       # 探索性实验（不追求整洁）
├── projects/        # 端到端项目：有自己的 README、依赖、入口
│   └── teaching-agent/        # Teaching 知识体系 m01-m11 + 可视化 + 评测（实际代码块）
├── evals/           # 评测集、评测脚本、trace 样本
├── data/            # 数据集 / PDF / 索引等大文件（不进 git）
├── resources/       # 外部资源索引：课程、博客、文档、社区
├── templates/       # 笔记与项目模板
└── archive/         # 过时但想留着的
```

| 路径 | 放什么 | 判断标准 |
|---|---|---|
| `docs/` | 结构化笔记、论文笔记、学习日志 | 是「知识」，不是「能跑的东西」 |
| `code/` | 每个主题下的最小可运行示例 | 10~100 行、能单独跑、只服务一个知识点 |
| `notebooks/` | 数据探索、临时画图、对比实验 | 还在试错，不保证整洁 |
| `projects/` | 完整小系统 | 有 README、有入口、能交付 |
| `evals/` | 测试用例、评分脚本 | 用来证明「改了之后有没有变好」 |
| `data/` | 语料、PDF、本地索引、权重 | 体积大或不便公开 |
| `resources/` | 书单、课程、文章链接 | 只是索引，不复制正文 |

## 主题编号（`docs/` 与 `code/` 同编号）

| 编号 | 主题 | 一句话 |
|---|---|---|
| 01 | [foundations](docs/01-foundations/) | LLM 能力边界、Agent 与 Workflow 的区别、ReAct 循环 |
| 02 | [prompt-context](docs/02-prompt-context/) | 提示结构、上下文工程、结构化输出 |
| 03 | [tool-use](docs/03-tool-use/) | Function Calling、工具设计、MCP |
| 04 | [memory-rag](docs/04-memory-rag/) | 短期/长期记忆、检索、知识库 |
| 05 | [planning](docs/05-planning/) | 任务分解、反思、搜索与自我修正 |
| 06 | [multi-agent](docs/06-multi-agent/) | 角色分工、通信、编排与冲突 |
| 07 | [frameworks](docs/07-frameworks/) | LangGraph / CrewAI / DeepSeek Harness 等选型 |
| 08 | [eval-observability](docs/08-eval-observability/) | 评测集、LLM-as-judge、tracing |
| 09 | [safety-guardrails](docs/09-safety-guardrails/) | 注入攻击、权限、人类确认、合规 |
| 10 | [production](docs/10-production/) | 成本、延迟、并发、部署、监控 |
| 11 | [harness-engineering](docs/11-harness-engineering/)（11 章 ☑） | Harness 架构、循环、上下文、工具、环境、恢复、安全、评测 |

## 学习路线（摘要）

**阶段一 · 把循环手写一遍（约 1~2 周）**
- [ ] 01 + 02：能解释 Agent / Workflow / ReAct 的差异，写出稳定可解析的 prompt
- [ ] 03：不借助框架，手写一次 function calling 循环
- 交付物：`code/` 里一个 200 行以内的 mini agent

**阶段二 · 把能力补齐（约 3~4 周）**
- [ ] 04 + 05：加检索与记忆，做一次任务分解
- [x] 07：用 LangGraph / CrewAI / DeepSeek Harness 重写阶段一的 mini agent，对比差异
  - ✅ [医疗教学 Agent](code/07-frameworks/medical-education/)：LangGraph vs CrewAI 对照实现
  - ✅ [Harness 扩展示例](code/07-frameworks/harness-examples/)：DSH 插件开发三种方式
- 交付物：`projects/` 里第一个能解决真实问题的小工具

**阶段三 · 把工程做扎实（约 4~6 周）**
- [ ] 06 + 08：多智能体协作 + 一套自己的评测集
- [ ] 09 + 10：护栏、成本与延迟优化
- 交付物：一个带评测报告的项目

详细清单与验收标准见 [docs/00-roadmap.md](docs/00-roadmap.md)。

## 约定

- 目录名、文件名用英文 `kebab-case`；笔记正文用中文。
- 每篇笔记以 [templates/note.md](templates/note.md) 开头（结论先行 + 待验证问题）。
- 每个代码示例必须能直接运行；文件顶部写清「目的 / 运行方式 / 依赖」。
- 一个知识点没亲手跑通之前，不写进 `docs/`（避免抄来的假笔记）。
- 完成一个主题，更新 [docs/README.md](docs/README.md) 的状态列。
- 大文件（PDF、数据集、权重）不进 git；论文索引放 [docs/papers/](docs/papers/)。

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/jsjchai/agent-lab.git
cd agent-lab

# 创建虚拟环境（推荐用 uv，更快）
uv venv .venv --python 3.11
source .venv/bin/activate

# 安装医疗教学示例依赖
uv pip install -r code/07-frameworks/medical-education/requirements.txt

# 复制环境变量模板（可选，用于真实模型）
cp .env.example .env
```

依赖按主题需要再装，别提前堆一个巨大的 requirements。代码用到的库版本，记在对应主题目录的 `requirements.txt`。

### 运行示例

**Teaching Agent 知识体系（离线 mock，一键验收 11 模块）**
```bash
uv pip install -r projects/teaching-agent/requirements.txt
cd projects/teaching-agent
../../.venv/bin/python run_all.py          # 11/11 通过，约 1 秒
../../.venv/bin/python m05_workflow.py     # 活动创建全流程（含重启恢复）
../../.venv/bin/python webui/server.py     # 可视化页面 http://127.0.0.1:7871
```
详见 [projects/teaching-agent/README.md](projects/teaching-agent/README.md)（含 Java→Python 替代对照表）。

**医疗教学 Agent（离线 mock）**
```bash
cd code/07-frameworks/medical-education
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py
AGENT_LLM=mock ../../../.venv/bin/python crewai_teaching_activity.py
```

**可视化界面**
```bash
cd code/07-frameworks/medical-education
../../../.venv/bin/python webui/server.py
# 打开 http://127.0.0.1:7861
```

**使用本地小模型（Ollama）**
```bash
# 先启动 Ollama 并拉取模型
ollama pull qwen2.5:7b

# 运行
export AGENT_LLM=openai
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
../../../.venv/bin/python langgraph_case_agent.py --model qwen2.5:7b
```

**DeepSeek Harness 插件**

Harness 示例是配置型插件，通过 DSH Web GUI 安装：
1. 打开 DSH → Plugins → Add plugin
2. 选择 `code/07-frameworks/harness-examples/` 下的任一目录
3. 启用后即可使用

详见 [harness-examples/README.md](code/07-frameworks/harness-examples/README.md)。
