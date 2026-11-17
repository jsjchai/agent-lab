# 09 · 安全与护栏 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)。

## 学什么

- 多租户 / 最小权限 / 二次鉴权；身份来自可信认证链路，不采信模型生成字段。
- **Prompt Injection** 防护（用户输入 + 检索文档间接注入）。
- 一次性确认凭证：绑定用户/租户/草稿哈希/有效期，防重放/防篡改。
- Agent 不直接写业务表；写操作由原业务服务执行；关键调用可审计。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| 12 项安全测试套件 | [m07](../../projects/teaching-agent/m07_security.py) | `cd projects/teaching-agent && ../../.venv/bin/python m07_security.py` |
| 安全上下文 + 凭证存储 | [common/security.py](../../projects/teaching-agent/common/security.py) | — |

实测越权拦截率 100%，凭证不可重放，12/12 安全测试通过。

## 对应笔记

→ [docs/09-safety-guardrails](../../docs/09-safety-guardrails/README.md)
