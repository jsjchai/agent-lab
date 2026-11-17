# 03 · 工具调用 — 代码导航

> 本目录是**主题导航**。可运行示例集中在 [projects/teaching-agent/](../../projects/teaching-agent/README.md)
> 与 [code/07-frameworks/harness-examples/](../07-frameworks/harness-examples/README.md)。

## 学什么

- 工具白名单 + 参数 Schema 校验 + 调用次数限制。
- **每次调用重新鉴权**；不信任模型提供的 userId/tenantId。
- P0 不开放写工具；工具只返回最小数据；调用有审计。
- MCP：把外部服务标准化为工具（见 harness 示例）。

## 跑什么

| 示例 | 文件 | 运行命令 |
|---|---|---|
| 业务工具白名单/权限/审计 | [m04](../../projects/teaching-agent/m04_tools.py) | `cd projects/teaching-agent && ../../.venv/bin/python m04_tools.py` |
| DSH 自定义工具插件 | [medical-tool-plugin](../07-frameworks/harness-examples/medical-tool-plugin/index.js) | 见 [harness README](../07-frameworks/harness-examples/README.md) |
| MCP Bundle 接外部工具 | [mcp-bundle-example](../07-frameworks/harness-examples/mcp-bundle-example/cordis.patch.yml) | 同上 |

## 对应笔记

→ [docs/03-tool-use](../../docs/03-tool-use/README.md)
