# _shared · 公共层 — 代码导航

> 跨示例复用的公共代码集中在 [projects/teaching-agent/common/](../../projects/teaching-agent/common/)，
> 医疗示例的公共层在 [code/07-frameworks/medical-education/common/](../07-frameworks/medical-education/common/)。
> 本目录按约定保留为公共层索引，避免在各示例里复制粘贴。

## 公共模块

| 模块 | 文件 | 职责 |
|---|---|---|
| LLM 适配层 | [common/llm.py](../../projects/teaching-agent/common/llm.py) | mock/openai 双后端、实例级模型选择、结构化输出校验重试、向量、Token 统计 |
| 安全上下文 | [common/security.py](../../projects/teaching-agent/common/security.py) | 可信认证、SecurityContext、一次性确认凭证（内存/SQLite）、审计 |
| 业务服务模拟 | [common/business.py](../../projects/teaching-agent/common/business.py) | 活动规则/校验/创建 API/幂等（Agent 不直接写表） |

## 设计原则

- 业务流程不绑定模型供应商：切换 mock ↔ 真实模型，业务代码不动。
- 关键字段确定性兜底：模型负责语义，代码负责格式与边界（见 m02 归一化）。
- 安全上下文来自认证链路，不采信模型生成的身份字段。
