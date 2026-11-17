# 04 · 记忆与检索（RAG）— 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)。

## 学什么

- RAG 全流程：解析 → Chunk → Embedding → 索引 → 混合检索 → Rerank → 引用回答。
- **检索阶段 ACL**（租户 + 组织过滤），不只靠 Prompt 保密。
- 引用必须回溯真实片段；无依据明确拒答。
- 索引版本：不同向量模型/维度不能混用。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| RAG（本地索引替代 Milvus） | [m06](../../projects/teaching-agent/m06_rag.py) | `cd projects/teaching-agent && ../../.venv/bin/python m06_rag.py` |
| 知识文档（含 ACL 元数据） | [data/knowledge](../../projects/teaching-agent/data/knowledge/) | — |

实测 Recall@3 / 引用准确率 / 拒答率均 100%（mock）；真实 bge-m3 + 7B 同样达标。

## 对应笔记

→ [docs/04-memory-rag](../../docs/04-memory-rag/README.md)
