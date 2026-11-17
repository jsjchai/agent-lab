# 外部资源索引

规则：**只放链接和一句话评价，不复制正文。** 看到好内容先记这里，值得深挖再写成 `docs/` 里的笔记。

状态标记：☐ 待读 ｜ ◐ 在读 ｜ ☑ 已读并写了笔记（附链接）

## 官方文档 / 规范

| 资源 | 说明 | 状态 |
|---|---|---|
| [LangGraph](https://langchain-ai.github.io/langgraph/) | 图式工作流，State/Checkpoint/interrupt，本仓库 m05 与医疗示例所用 | ☑ |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | 模型接入，替代 Spring AI ChatClient（见 common/llm.py） | ☑ |
| [Pydantic](https://docs.pydantic.dev/) | DTO + 校验，替代 Bean Validation（见 m01） | ☑ |
| [FastAPI](https://fastapi.tiangolo.com/) | SSE/REST 接口，替代 Spring WebFlux（见 m03/webui） | ☑ |
| [MCP 规范](https://modelcontextprotocol.io/) | 工具标准化协议，harness MCP Bundle 所用 | ☑ |
| [Ollama](https://ollama.com/docs) | 本地模型运行，OpenAI 兼容接口（7B/8B 实测） | ☑ |
| [Milvus](https://milvus.io/docs) | 生产向量库（本仓库用 numpy 本地索引替代演示） | ☐ |
| [vLLM](https://docs.vllm.ai/) | 私有化推理部署（P1，见 docs/10） | ☐ |
| [Spring AI](https://docs.spring.io/spring-ai/reference/) | 源文档 Java 技术栈参照（本仓库用 Python 等价物） | ☐ |
| [LangGraph4j](https://github.com/langgraph4j/langgraph4j) | Java 图式工作流候选（源文档 §6） | ☐ |

## 评测与可观测

| 资源 | 说明 | 状态 |
|---|---|---|
| [Langfuse](https://langfuse.com/docs) | LLM 追踪/评测平台（生产可观测选型） | ☐ |
| [Ragas](https://docs.ragas.io/) | RAG 评测指标（Recall/引用准确率，见 m06/m08） | ☐ |
| [DeepEval](https://docs.confident-ai.com/) | LLM 评测框架（确定性断言 + LLM-as-Judge） | ☐ |

## 课程与教程

| 资源 | 说明 | 状态 |
|---|---|---|
|  |  |  |

## 博客与工程文章

| 资源 | 一句话收获 | 状态 |
|---|---|---|
|  |  |  |

## 论文

→ 单独维护在 [docs/papers/](../docs/papers/README.md)

## 社区 / 榜单 / 数据集

| 资源 | 说明 |
|---|---|
|  |  |

## 选型核验清单（源文档 §15）

正式立项/升级前重新核对：最近 Release 与发布频率、近 90 天提交、Issue/PR 响应、维护者与策略、
安全漏洞修复、兼容矩阵、Checkpoint/持久化/Interrupt-Resume 能力、文档与升级指南、能否用自有接口隔离框架。
**GitHub 有提交 ≠ 适合生产。**
