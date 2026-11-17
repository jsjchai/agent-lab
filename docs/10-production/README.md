# 10 · 工程化与上线

**目标**：把 demo 变成能算清成本、扛得住并发、挂了能查的东西。

## 关键问题
- 一次任务平均多少 token、多少钱、多少秒？瓶颈在哪一步？
- 哪些环节可以缓存 / 并行 / 换小模型？
- 失败重试怎么做才不会重复副作用？
- 日志要记什么，事后才能复盘？

## 产出
- [ ] 一份成本基线：单任务 token / 费用 / 延迟
- [ ] 一次优化前后对比（缓存、裁剪上下文、并行、小模型分流）
- [ ] 一个最小可用的运行封装：超时、重试、降级、日志
- [ ] 一页「如果明天要给别人用，我还缺什么」清单

## Teaching 场景落地（源文档 §9 模型路由 + §10 分布式可靠性）

配套可运行示例：[m09 模型路由](../../projects/teaching-agent/m09_router.py)、[m10 可靠性](../../projects/teaching-agent/m10_reliability.py)

### 模型部署与路由（§9）
- 云端：API Key / Base URL / 模型名 / 兼容协议 / Token 计费 / RPM/TPM / 并发 / 超时 / 限流 / 重试 / 数据合规。
- 私有化：vLLM / GPU 显存 / FP16/BF16 / AWQ/GPTQ/INT4 / KV Cache / Continuous Batching / Tensor Parallel。首期重点是部署、调用、监控、评估，不要求训练或优化内核。
- 路由维度：任务类型 / 数据合规 / 质量 / 成本 / 延迟 / 故障状态。
- **PRIVATE_ONLY 任务不能因私有模型故障自动回退云端**（m09 用 ComplianceError 强制）。

验收：至少两种模型配置；按任务路由；统计调用量/成本/延迟/失败率；故障回退不绕过合规。

### 异步任务可靠性（§10，SQLite 替代 RocketMQ+MySQL）
- Outbox：库提交与消息发送的一致性（m10 同事务写 tasks+outbox）。
- 幂等键：避免重复执行（唯一约束去重）。
- 租约 + 心跳：识别异常退出 Worker。
- 指数退避：控制重试。
- 死信队列 / 转人工：无法自动恢复的任务（NEEDS_HUMAN）。
- 补偿 / 取消：定义可取消边界。

任务状态机：`PENDING → QUEUED → RUNNING → SUCCEEDED / RETRY_WAIT / FAILED / CANCELLED / NEEDS_HUMAN`。

验收：重复消息不产生重复业务操作；Worker 宕机后任务可恢复；失败任务可追踪、重试或转人工。m10 全部断言通过。
