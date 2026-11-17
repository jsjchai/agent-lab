# 02 · Prompt 与上下文工程

> 对应源文档 §4 · 代码模块 [`m02_intent_slots.py`](../m02_intent_slots.py) · 运行：`../../.venv/bin/python m02_intent_slots.py`

## 一、这是什么 / 为什么重要

Agent 的第一步是**理解用户想干什么**。源文档 §4 的 Teaching 实战：面对
「帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人」，系统要识别活动类型、主题、
时间、对象、主讲人，判断缺什么，决定哪些能查、哪些必须问，最终生成草稿而非直接创建。

本模块把这一步做成结构化输出：`intent / slots / missingFields / questions`，并解决两个工程难题——
**Prompt 变更如何不破坏既有行为**（版本管理 + 回归），以及**小模型输出漂移如何兜底**（确定性归一化）。

## 二、核心概念详解

### System / User Prompt 职责边界
System 定角色与输出契约（「你是意图识别模块，只输出 JSON，字段如下…」），User 给具体输入。
本项目 `SYSTEM_PROMPT` 固定契约，`build_messages` 把用户输入包进 user 消息。

### Prompt Template 与 Few-shot
`SYSTEM_PROMPT`（intent-v2）里给了**一个完整示例**（输入→输出 JSON），这是 few-shot，
显著提升小模型对 Schema 的遵守度。变量注入通过 `build_messages(user_text)` 完成。

### 槽位（Slots）与缺项（missingFields）
slots 是已抽取的字段（activity_type/subject/grade/date_text/audience/speaker_count/speakers）；
missingFields 是创建活动的必填项里还缺的。**关键设计：缺项由代码按必填字段重算，不信任模型给的命名**（见下）。

### Prompt 版本管理
`PROMPT_VERSION = "intent-v2"`。源文档要求「Prompt 变更触发回归测试」——改 prompt 必须升版本并跑
`REGRESSION_CASES`（21 条真实表达），确保不回归。

### Prompt Injection
用户输入或检索文档可能试图改写系统指令。本模块的防线是：输出必须通过 `_validate_intent` 结构校验，
且下游 [04 工具](04-工具调用与业务工具设计.md)/[07 安全](07-安全治理与人工确认.md) 不采信模型身份字段。注入防护详见 07。

## 三、代码实现解析

### 强 Schema 的 SYSTEM_PROMPT（intent-v2）

prompt 明确列出 slots 可用键、取值范围、missingFields 必须用英文键名，并给一个 few-shot 示例：

```text
slots 只能使用以下键（不要自创键名）：
- activity_type：教研活动 / 培训 / 公开课
- date_text：具体日期，如 "11月20日"/"明天"/"周二"。若只说"下周"这类模糊时间，
  不要填 date_text，改填 time_hint="下周"
- speakers：人名数组。不知道具体人名就不要填 speakers
missingFields：从 [activity_type, subject, date_text, audience, speakers] 中选仍缺的必填项，必须用英文键名。
示例输入：创建11月20日数学教研活动，面向三年级教师，主讲人：张三、李四
示例输出：{"intent":"create_activity","slots":{...},"missingFields":[],"questions":[]}
```

**为什么这样写**：小模型（7B）会自创中文键名、把模糊时间当日期。把键名/取值/示例写死，漂移大幅减少。

### _validate_intent：结构校验

```python
def _validate_intent(data: dict) -> str | None:
    if data.get("intent") not in {"create_activity", "knowledge_qa", "unknown"}:
        return "intent 须为 create_activity/knowledge_qa/unknown"
    if not isinstance(data.get("slots"), dict): return "slots 须为对象"
    if not isinstance(data.get("missingFields"), list): return "missingFields 须为数组"
    if not isinstance(data.get("questions"), list): return "questions 须为数组"
    return None
```

配合 `chat_json` 重试，保证拿到结构合法的 JSON。

### _normalize：确定性归一化（核心）

模型负责语义抽取，**代码负责清洗与边界**：

```python
def _normalize(result: dict, user_text: str) -> dict:
    # 1. 清洗槽位：speakers 字符串→数组、去空；speaker_count "两位"→2
    # 2. 日期确定性兜底：取文本中「最后一个具体日期」覆盖（澄清/修正追加在末尾，应优先）
    specific = list(_DATE_RE.finditer(user_text))
    if specific:
        clean["date_text"] = specific[-1].group(1)
    elif "date_text" in clean and not _DATE_RE.fullmatch(str(clean["date_text"])):
        clean.pop("date_text")        # 模糊日期（下周）视为缺项，触发澄清
    # 3. 缺项由代码按必填字段重算，不信任模型的 missingFields 命名
    missing = [f for f in _REQUIRED if f not in clean]
```

**为什么这样写**：实测 7B 有三类漂移——键名/类型乱（`speakers:""`、`speaker_count:"两位"`）、
缺项用中文命名、补充澄清后仍沿用旧日期。归一化逐一纠正，保证下游工作流拿到规范结构。
这正是源文档 §3「未经校验的输出不得进入业务流程」的落地。

### recognize：抽取入口

```python
def recognize(llm, user_text):
    result = llm.chat_json(build_messages(user_text), validate=_validate_intent, retries=2)
    if "_error" in result:                      # 重试仍失败
        return mock_extract_intent(user_text)   # 回退规则抽取，保证流程不崩
    return _normalize(result, user_text)
```

## 四、工程要点与常见坑

| 现象 | 原因 | 对策 |
|---|---|---|
| 槽位键名用中文、类型乱 | 小模型不守 Schema | 强 Schema prompt + `_normalize` 清洗 |
| missingFields 命名不规范 | 模型自创字段名 | 缺项由代码按 `_REQUIRED` 重算 |
| 补充「11月20日」后仍抽成「下周」 | 模型不优先最新澄清 | 正则取文本最后一个具体日期覆盖 |
| 模糊日期被当具体日期 | 「下周」不可解析 | `fullmatch` 检测，模糊则视为缺项触发澄清 |
| JSON 彻底解析失败 | 模型严重漂移 | 回退 `mock_extract_intent` 规则抽取 + 告警 |
| 改 prompt 后行为回归 | 无回归测试 | `PROMPT_VERSION` + 21 条 `REGRESSION_CASES` |

## 五、验收与测试

`selftest()` 跑 `run_regression`，要求 21 条真实表达**全过**：

```python
def selftest():
    passed, total = run_regression(LLM("mock"))
    assert passed == total
```

每条用例断言：intent 正确 + 期望槽位子集匹配 + 期望缺项 ⊆ 实际缺项（正常创建还要求缺项为空）。
覆盖正常创建、缺项澄清、知识问答、未知意图等类别。

## 六、与其他模块的关系

- **被 [05 工作流](05-Agent工作流编排.md) 调用**：`extract` 节点用 `recognize` 抽取，缺项驱动 `clarify` 回环。
- 复用 [01](01-LLM基础与结构化输出.md) 的 `chat_json` 校验重试契约。
- 归一化后的 slots 交给 [04 工具](04-工具调用与业务工具设计.md) 的 `build_activity_draft`。
- 漂移程度被 [11 模型对比](11-模型横向对比.md) 量化为「槽位漂移次数」。

## 七、动手练习与延伸

1. 把 `SYSTEM_PROMPT` 的 few-shot 示例删掉，接 7B 跑 `run_regression`，对比准确率下降。
2. 在 `_normalize` 里关掉日期兜底（注释 `specific` 分支），用「下周…补充11月20日」观察工作流卡在 validation_error。
3. 新增 3 条真实表达到 `REGRESSION_CASES`，升 `PROMPT_VERSION` 到 v3，跑回归。

## 参考

- 源文档 §4「Prompt Engineering 与 Context Engineering」
- 项目内：[`m02_intent_slots.py`](../m02_intent_slots.py)、[01 结构化输出](01-LLM基础与结构化输出.md)、[05 工作流](05-Agent工作流编排.md)
