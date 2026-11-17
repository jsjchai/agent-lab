# 05 · Agent 工作流编排

> 对应源文档 §6 · 代码模块 [`m05_workflow.py`](../m05_workflow.py) · 运行：`../../.venv/bin/python m05_workflow.py`

## 一、这是什么 / 为什么重要

这是整个项目的**核心**：把前面各模块（意图抽取、工具、校验、安全）编排成一个完整的
「对话式创建活动」工作流。源文档 §6 的首期流程是：

```
用户输入 → 身份权限上下文 → 意图/字段抽取 → 缺项判断
   有缺项 → 向用户澄清并等待补充
   无缺项 → 调用只读业务工具 → 生成草稿 → 业务规则校验
         → 展示草稿 → 用户确认 → 调用既有业务 API 创建 → 返回结果
```

关键设计决策（源文档 §6）：**首期单 Agent + 显式工作流，不急于 Multi-Agent**；状态必须持久化；
关键步骤人工确认（HITL）；最终写操作由原业务服务执行。本模块用 **LangGraph** 把这些落成
State/Graph/条件边/Checkpoint/interrupt。

## 二、核心概念详解

### Agent vs Workflow vs ReAct
- **Workflow**：程序定义步骤与分支的确定性流程（本模块）。
- **Agent/ReAct**：模型自主决定下一步（推理→行动→观察循环）。
- 源文档建议首期用 Workflow：流程确定、可控、可审计；把模型的自主性限制在「抽取/生成」环节。

### State（状态）
`FlowState` 是任务执行过程的数据：task_id、user_text、slots、missing、draft、errors、
clarify_rounds、status、activity_id、trace。节点只返回**增量**，框架负责合并。

### Graph / 条件边 / 回环
节点（extract/clarify/gather/draft/validate/fix/confirm/create/fail）+ 边构成图。
**条件边**（`add_conditional_edges`）按状态决定走向；`clarify→extract`、`fix→extract` 形成**回环**。

### Checkpoint（检查点）
`SqliteSaver` 把状态持久化到 SQLite。服务重启后用 `thread_id` 恢复——这是「长任务状态不能只依赖内存」的落地。

### HITL（Human-in-the-loop）
`interrupt()` 暂停流程等人输入；`Command(resume=value)` 恢复。本模块有三处中断：
澄清（clarification）、校验修正（validation_error）、确认（confirmation）。

### 防无限循环
`MAX_CLARIFY_ROUNDS=3`：澄清/修正超过 3 轮转 fail；LangGraph `recursion_limit` 兜底。

## 三、代码实现解析

### FlowState：共享状态

```python
class FlowState(TypedDict, total=False):
    task_id: str
    user_text: str
    slots: dict
    missing: list
    draft: dict
    errors: list
    clarify_rounds: int
    status: str
    activity_id: str
    confirm_token: str
    trace: Annotated[list, operator.add]   # 节点轨迹，operator.add 表示追加而非覆盖
```

`trace` 用 `Annotated[list, operator.add]`——每个节点追加一条记录，供可视化动画展示执行路径。

### 条件边：缺项判断与校验分流

```python
def route_extract(state):
    if not state.get("missing"): return "gather"          # 信息齐 → 收集
    if state.get("clarify_rounds", 0) >= MAX_CLARIFY_ROUNDS: return "fail"
    return "clarify"                                       # 缺项 → 澄清

def route_validate(state):
    if not state.get("errors"): return "confirm"          # 校验过 → 确认
    if state.get("clarify_rounds", 0) >= MAX_CLARIFY_ROUNDS: return "fail"
    return "fix"                                           # 有错 → 修正
```

### interrupt：三种人工中断

```python
def clarify(state):
    answer = interrupt({"type": "clarification", "questions": state["questions"]})
    return {"user_text": state["user_text"] + "。补充：" + str(answer),
            "clarify_rounds": state.get("clarify_rounds", 0) + 1}

def confirm(state):
    token = tokens.issue(ctx, state["draft"])             # 签发一次性凭证
    payload = interrupt({"type": "confirmation", "draft": state["draft"], "token": token})
    tokens.consume(str(payload), ctx, state["draft"])     # 校验五要素 + 一次性
    return {"confirm_token": str(payload), "status": "confirmed"}
```

`interrupt()` 抛出中断暂停图；用户作答后 `Command(resume=value)` 把值送回，`interrupt()` 返回该值继续。

### 图的组装

```python
g.add_edge(START, "extract")
g.add_conditional_edges("extract", route_extract, {"gather":"gather","clarify":"clarify","fail":"fail"})
g.add_edge("clarify", "extract")        # 回环
g.add_edge("gather", "draft")
g.add_edge("draft", "validate")
g.add_conditional_edges("validate", route_validate, {"confirm":"confirm","fix":"fix","fail":"fail"})
g.add_edge("fix", "extract")            # 回环
g.add_edge("confirm", "create")
g.add_edge("create", END)
g.add_edge("fail", END)
return g.compile(checkpointer=checkpointer)
```

每个节点用 `traced(name, fn)` 包装，执行后追加 `trace`。`ctx` 通过闭包注入（每次来自认证链路），**不存进 checkpoint**。

### start_task / resume_task：跨进程恢复

```python
def resume_task(task_id, user, value, db, tokens=None):
    ctx = authenticate(user)                    # 重新认证
    conn, saver = _open(db)                     # 重建 saver（模拟重启）
    graph = build_graph(ctx, LLM(), reg, tokens or ConfirmTokenStore(), saver)
    config = {"configurable": {"thread_id": task_id}}
    pre = graph.get_state(config)
    if not pre.tasks or not any(t.interrupts for t in pre.tasks):
        raise AuthError("任务已结束或不存在待处理中断，无法继续")   # 防重放
    graph.invoke(Command(resume=value), config)
```

**为什么这样写**：resume 重新认证 + 重建图，状态从 SQLite 恢复，证明「服务重启可续跑」；
先检查有无待处理中断，已结束任务拒绝继续（防止对已完成任务重放凭证）。

## 四、工程要点与常见坑

| 现象 | 原因 | 对策 |
|---|---|---|
| 重启后任务丢失 | 状态只在内存 | SqliteSaver 持久化 + thread_id 恢复 |
| 对已完成任务重放凭证 | 无终态检查 | resume 前检查待处理中断，无则拒绝 |
| 澄清无限循环 | 无轮数上限 | MAX_CLARIFY_ROUNDS=3 → fail |
| 模型身份混入状态 | ctx 存进 checkpoint | ctx 闭包注入，每次重新认证 |
| 确认后被篡改草稿 | 凭证未绑定草稿 | consume 校验草稿哈希（见 07） |
| 直接写业务表 | Agent 越权 | create 调 `business.create_activity_api`（幂等） |

## 五、验收与测试

`selftest()` 完整走一遍并断言：

```python
r = start_task("u1", "帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人", db)
assert r["interrupt"]["type"] == "clarification"          # 缺项 → 澄清
r = resume_task(task_id, "u1", "11月20日，主讲人：张三、李四", db, tokens)
assert r["interrupt"]["type"] == "confirmation"           # 补齐 → 确认
r = resume_task(task_id, "u1", token, db, tokens)
assert r["values"]["status"] == "done"                    # 确认 → 创建
assert business.activity_count() == 1
# 重放凭证被拒绝，且不会重复创建
try: resume_task(task_id, "u1", token, db, tokens); raise AssertionError()
except AuthError: pass
assert business.activity_count() == 1
```

对应源文档 §6 POC 验收：状态持久化、重启恢复、补充续跑、人工中断恢复、重放拒绝。

## 六、与其他模块的关系

- 调 [02 意图](02-Prompt与上下文工程.md) `recognize` 抽取（extract 节点）。
- 调 [04 工具](04-工具调用与业务工具设计.md) gather/draft/validate。
- 用 [07 安全](07-安全治理与人工确认.md) 的 `authenticate`/`ConfirmTokenStore`。
- create 调 `common/business.py` 的 `create_activity_api`（幂等）。
- [webui](../webui/server.py) 把 start/resume 包成 HTTP 接口做交互可视化。

## 七、动手练习与延伸

1. 用 CLI 分步跑：`start` → `resume --input` → `resume --confirm-token`，观察跨进程恢复。
2. 把 `MAX_CLARIFY_ROUNDS` 改成 1，输入始终缺项的需求，观察提前转 fail。
3. 删掉 resume 的「待处理中断检查」，对已完成任务重放 token，观察重复创建风险（再改回）。

## 参考

- 源文档 §6「Agent 与工作流编排」
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)（interrupt / Checkpoint）
- 项目内：[`m05_workflow.py`](../m05_workflow.py)、[04 工具](04-工具调用与业务工具设计.md)、[07 安全](07-安全治理与人工确认.md)
