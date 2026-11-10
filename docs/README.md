# 资料索引

状态：☐ 未开始 ｜ ◐ 进行中 ｜ ☑ 已掌握（能讲清 + 有代码产出）

| 编号 | 主题 | 要能回答的问题 | 代码 | 状态 |
|---|---|---|---|---|
| 01 | [foundations](01-foundations/) | Agent 和「带 if/else 的 Workflow」差在哪？ReAct 每一步在干什么？ | [code](../code/01-foundations/) | ☐ |
| 02 | [prompt-context](02-prompt-context/) | 同一模型，为什么上下文组织方式能决定成败？ | [code](../code/02-prompt-context/) | ☐ |
| 03 | [tool-use](03-tool-use/) | 模型怎么「决定」调工具？工具描述写不好会怎样？ | [code](../code/03-tool-use/) | ☐ |
| 04 | [memory-rag](04-memory-rag/) | 该记什么、记在哪、什么时候取？检索为什么会失效？ | [code](../code/04-memory-rag/) | ☐ |
| 05 | [planning](05-planning/) | 长任务怎么拆？什么时候该反思/重试？ | [code](../code/05-planning/) | ☐ |
| 06 | [multi-agent](06-multi-agent/) | 什么时候多智能体真的比单智能体好？ | [code](../code/06-multi-agent/) | ☐ |
| 07 | [frameworks](07-frameworks/) | 框架替你做了什么，代价是什么？ | [code](../code/07-frameworks/) | ☐ |
| 08 | [eval-observability](08-eval-observability/) | 怎么证明这一版比上一版强？ | [code](../code/08-eval-observability/) | ☐ |
| 09 | [safety-guardrails](09-safety-guardrails/) | 提示注入、越权操作怎么防？ | [code](../code/09-safety-guardrails/) | ☐ |
| 10 | [production](10-production/) | 怎么把延迟和成本压下来并稳定上线？ | [code](../code/10-production/) | ☐ |
| — | [papers](papers/) | 论文原文索引与阅读笔记 | — | — |
| — | [journal](journal/) | 学习日志：今天学了什么、卡在哪 | — | — |

## 怎么用这个目录

- 每个主题目录的 `README.md` 是门面：目标、关键问题、资料清单、产出清单。先读它再动手。
- 笔记命名 `YYYY-MM-DD-主题.md`（例：`2026-11-10-react-循环.md`），一篇只讲一件事。
- 笔记结论先行：开头写「一句话结论」，跑通后补「我的验证」。
- 读完一篇论文：在 [papers/README.md](papers/README.md) 加一行索引，笔记放 `papers/notes/`。
- 日志不是日记：只记「学到的一个点 + 卡住的一个点 + 下一步」，见 [journal/](journal/)。
