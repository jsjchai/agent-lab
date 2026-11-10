# agent-lab

Agent 学习与实践仓库：**资料在 `docs/`，小步实验代码在 `code/`，完整项目在 `projects/`。**

默认面向 LLM Agent（工具调用 / 检索 / 多智能体 / 评测）。如果以后要加强化学习 Agent，也放进对应的 `01-10` 主题或 `projects/`，结构不用改。

## 目录一览

```
agent-lab/
├── docs/            # 学习资料：路线图、主题笔记、论文、日志
├── code/            # 跟学代码：按主题编号，与 docs 一一对应
├── notebooks/       # 探索性实验（不追求整洁）
├── projects/        # 端到端项目：有自己的 README、依赖、入口
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
| 07 | [frameworks](docs/07-frameworks/) | LangGraph / OpenAI Agents SDK / Claude Agent SDK 等选型 |
| 08 | [eval-observability](docs/08-eval-observability/) | 评测集、LLM-as-judge、tracing |
| 09 | [safety-guardrails](docs/09-safety-guardrails/) | 注入攻击、权限、人类确认、合规 |
| 10 | [production](docs/10-production/) | 成本、延迟、并发、部署、监控 |

## 学习路线（摘要）

**阶段一 · 把循环手写一遍（约 1~2 周）**
- [ ] 01 + 02：能解释 Agent / Workflow / ReAct 的差异，写出稳定可解析的 prompt
- [ ] 03：不借助框架，手写一次 function calling 循环
- 交付物：`code/` 里一个 200 行以内的 mini agent

**阶段二 · 把能力补齐（约 3~4 周）**
- [ ] 04 + 05：加检索与记忆，做一次任务分解
- [ ] 07：用 LangGraph 或官方 SDK 重写阶段一的 mini agent，对比差异
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
git init
python3 -m venv .venv && source .venv/bin/activate    # 或用 uv
cp .env.example .env                                   # 填入自己的 API key
```

依赖按主题需要再装，别提前堆一个巨大的 requirements。代码用到的库版本，记在对应主题目录的 `requirements.txt`。
