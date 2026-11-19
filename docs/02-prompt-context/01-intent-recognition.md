# 01 · 意图识别：Agent 的第一道门

> 对应主题 [02-prompt-context](README.md)。代码锚点：[code/02-prompt-context/intent_recognition.py](../../code/02-prompt-context/intent_recognition.py)。
> 本章讲：用户一句话进来，系统如何判断「他想干什么」，并决定走哪条流程。

## 一、问题背景：不识别意图，后面全是错的

假设你做了一个「教学活动助手」，用户说：「帮我搞个下周的语文教研」。
如果不先识别意图，系统会怎样？

- **走错流程**：把「查询」当「创建」，或把「闲聊」当「建活动」，直接调错工具。
- **漏抽字段**：不知道这是「创建活动」，就不会去抽学科、日期、主讲人，后面草稿缺字段。
- **该问的不问**：用户没说日期，系统如果不判断「缺什么」，就会拿着半截信息去创建。
- **风险不可控**：创建类操作有副作用，识别错了可能建错活动、发错通知。

**意图识别（Intent Recognition）就是 Agent 的第一道门**：先判断「想干什么」（intent），
再抽取「需要哪些信息」（slots），判断「缺什么要问」（clarification），最后决定「执行 / 澄清 / 转人工」。
这道门没做好，后面所有步骤都会放大错误。

## 二、核心概念：四个词说清意图识别

**意图（Intent）**：用户想完成的任务类别，如 `create_activity`（建活动）、`query_activity`（查活动）、
`knowledge_qa`（问知识）、`chitchat`（闲聊）。意图是一个**有限枚举**，不是自由文本。

**槽位（Slot）**：完成该意图所需的参数，如学科、日期、主讲人。槽位有**必填**与**可选**之分，
必填缺失就要澄清。

**多意图（Multi-intent）**：一句话可能包含多个意图，如「查一下上周活动，再帮我建一个」= 查询 + 创建。
好的识别要能输出**意图数组**，而不是硬选一个。

**置信度（Confidence）**：系统对这次识别的把握。低于阈值就不该硬走，而应**转人工**或**追问**。
这是「不确定就别猜」的工程原则。

**通道（Route）：动作意图 vs 知识意图**。识别出意图后，最关键的一步是判断**这次该调接口还是走问答**。
这是两条完全不同的处理路径：

| 通道 | 含义 | 意图 | 典型表达 |
|---|---|---|---|
| `api_write` | 调业务接口·写（改状态，需鉴权/确认） | create_activity | 「帮我建一个教研活动」「删除这条活动」 |
| `api_read` | 调业务接口·读（查我的结构化数据） | query_activity | 「查一下我的活动」「有哪些公开课」 |
| `knowledge` | 走 RAG 知识问答（只读知识，不改状态） | knowledge_qa | 「什么是教研活动」「创建流程是什么」 |
| `chat` | 闲聊 / 兜底 | chitchat | 「今天天气不错」 |

判据不是「有没有动作词」，而是**用户是要系统做事，还是想要信息**：
- **要做事**（祈使 + 具体对象 + 可执行动作）→ 调接口。
- **要信息**（方法/规则/概念/为什么）→ 问答。
- 陷阱：**「如何创建活动」含动作词「创建」，但它是问方法，应走问答，不能调创建接口**。

> 术语辨析：**意图识别 ≠ 槽位抽取**。意图是「做什么」（分类问题），槽位是「用什么做」（信息抽取问题）。
> 两者常一起做，但失败模式不同：意图错是「方向错」，槽位错是「参数错」。

## 三、工作原理：一条完整流水线

```text
用户文本
  → 分类器（三选一：规则 / 向量 / LLM 结构化）
  → 原始输出（intents / slots / confidence）
  → 归一化（枚举映射 / 类型纠正 / 键名收窄 / 置信度钳制）
  → 路由（判定走哪条通道：api_write / api_read / knowledge / chat）
  → 决策（confidence < 阈值 → 转人工；写操作缺必填 → 澄清；否则 → 执行）
  → 交给下游（写接口 / 读接口 / RAG / 闲聊）
```

**怎么判断「调接口」还是「问答」？** 用**确定性信号**判据，按优先级：

| 优先级 | 判据 | 结论 | 例子 |
|---|---|---|---|
| 1 | 方法/解释问句（如何/怎么/为什么/是什么/规定/流程）+ 无「帮我/给我」 | `knowledge` | 「如何创建活动」「培训有什么规定」 |
| 2 | 写动作（创建/删除/修改/发布/安排） | `api_write` | 「帮我建一个教研活动」 |
| 3 | 数据指代（我的/查一下/列表/查询）或查询意图 | `api_read` | 「查一下我的活动列表」 |
| 4 | 知识意图 | `knowledge` | 「什么是教研活动」 |
| 5 | 其余 | `chat` | 「今天天气不错」 |

**为什么优先级 1 要在最前？** 因为它专门处理陷阱：「**如何创建活动**」同时含「创建」（写动作）和「如何」（方法问句）。
若按「有动作词就调接口」，就会错误地调创建接口。把「方法问句」放最高优先级，能纠正这类误判——
这正是路由层存在的意义：**用确定性信号纠正分类器的语义误判**。

三种分类器的取舍（本 demo 对照前两种）：

| 方式 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **规则（关键词）** | 便宜、确定、可解释、零延迟 | 同义改写就漏，维护关键词表累 | 意图少、表达固定、作为兜底 |
| **向量分类** | 能理解语义相似，比规则稳 | 需训练/标注，边界意图易混 | 意图多、有标注数据 |
| **LLM 结构化** | 理解同义表达、能多意图、可解释 | 会漂移（格式/枚举）、有成本延迟 | 表达开放、意图复杂 |

**为什么 LLM 方案必须配归一化？** 因为 LLM 会「漂移」：把 `create_activity` 写成 `create`、
把 `speakers` 数组写成 `"张三、李四"` 字符串、把置信度写成 `1.7`。这些在 demo 里被**故意模拟**，
归一化负责修：别名映射、字符串转数组、钳制到 [0,1]。**模型负责语义，代码负责边界**——这是本章最重要的结论。

## 四、架构与流程

```mermaid
flowchart LR
    U["用户文本"] --> C{"分类器"}
    C -->|规则| R["intents/slots/conf"]
    C -->|LLM结构化| L["原始JSON"]
    L --> N["归一化<br/>枚举/类型/键名/置信度"]
    R --> N
    N --> RT{"路由：接口 or 问答"}
    RT -->|"方法问句"| K["knowledge<br/>RAG 知识问答"]
    RT -->|"写动作"| W["api_write<br/>业务写接口"]
    RT -->|"数据查询"| RD["api_read<br/>业务读接口"]
    RT -->|"无明确意图"| CH["chat<br/>闲聊/兜底"]
    W --> D{"决策"}
    D -->|conf<阈值| H["转人工"]
    D -->|缺必填| Q["澄清追问"]
    D -->|完整| E["执行"]
```

**图解关键**：无论用哪种分类器，原始输出都先过**归一化**，再过**路由**决定通道（接口 or 问答）。
路由是「接口/问答」的分水岭：`api_write`/`api_read` 走业务接口，`knowledge` 走 RAG，`chat` 兜底。
写接口再经**决策**（低置信转人工、缺槽位追问、齐全才执行）。归一化是「LLM 方案能上生产」的前提；
路由是「不误调接口」的保险。

## 五、代码实现：把流水线跑出来

[intent_recognition.py](../../code/02-prompt-context/intent_recognition.py) 约 220 行，离线可跑：

```bash
cd code/02-prompt-context && ../../.venv/bin/python intent_recognition.py
```

**实测输出**（节选）：

```text
输入：帮我搞个下周的语文教研
  规则 : ['create_activity'] conf=0.75 slots=['activity_type','subject']
  LLM  : ['create_activity'] conf=0.72 slots=['activity_type','subject']（已归一化）
  决策 : clarify — 缺必填槽位

评测（标注集）：
  规则基线准确率： {'accuracy': 0.9, 'n': 10}
  LLM 结构化准确率： {'accuracy': 1.0, 'n': 10}

小模型漂移演示（原始输出 → 归一化）：
  原始： {"intents":["create"],"slots":{"speakers":"张三、李四"},"confidence":1.7}
  归一化： {"intents":["create_activity"],"slots":{"speakers":["张三","李四"]},"confidence":1.0}
  → 意图别名映射 / 主讲人字符串转数组 / 置信度钳制到 1.0
```

**关键代码讲解**——归一化（本章核心）：

```python
INTENT_ALIASES = {"create": "create_activity", "query": "query_activity", "qa": "knowledge_qa"}

def normalize(raw: str) -> dict:
    data = _extract_json(raw)                      # 兼容 ```json 围栏
    intents = [INTENT_ALIASES.get(str(i).strip(), str(i).strip()) for i in intents]  # 别名映射
    intents = [i for i in intents if i in INTENTS] or ["chitchat"]                   # 收窄到合法枚举
    for k, v in slots_in.items():
        if k not in SLOT_KEYS: continue            # 键名收窄：自创键丢弃
        if k == "speakers" and isinstance(v, str):  # 类型纠正：字符串→数组
            v = re.split(r"[、和,]", v)
    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))  # 钳制
```

三个动作对应三类漂移：**别名映射**修枚举、**键名收窄**丢弃自创键、**类型纠正+钳制**修类型。
`selftest()` 逐条断言这些修复，并验证「LLM 准确率 ≥ 规则准确率」。

**关键代码讲解**——路由（接口 vs 问答）：

```python
WRITE_WORDS = ("创建", "安排", "组织", "删除", "修改", "发布", "搞个", "弄个")
METHOD_WORDS = ("如何", "怎么", "为什么", "是什么", "规定", "流程", "？")
SELF_DATA_WORDS = ("我的", "查一下", "查询", "列表", "记录")

def route(text, result):
    method = _hit(text, METHOD_WORDS)          # 方法/解释问句信号
    write = _hit(text, WRITE_WORDS)            # 写动作信号
    self_data = _hit(text, SELF_DATA_WORDS)    # 数据指代信号
    if method and not any(w in text for w in ("帮我", "给我", "替我")):
        return {"route": "knowledge", "reason": "方法/解释类问句，走知识问答"}
    if write or "create_activity" in result["intents"]:
        if not method:
            return {"route": "api_write", "reason": "含写动作，走业务写接口"}
    if self_data or "query_activity" in result["intents"]:
        return {"route": "api_read", "reason": "查询结构化业务数据，走读接口"}
    if "knowledge_qa" in result["intents"] or method:
        return {"route": "knowledge", ...}
    return {"route": "chat", ...}
```

**实测陷阱纠正**（关键的「含动作词但问方法」）：

```text
「如何创建教研活动？」
  意图=['create_activity', 'knowledge_qa'] → 通道=knowledge（RAG问答）
  理由：方法/解释类问句（如何/怎么/规定/流程），走知识问答
「帮我创建下周的数学教研活动」
  意图=['create_activity'] → 通道=api_write（业务写接口）
「查一下我的活动列表」
  意图=['query_activity'] → 通道=api_read（业务读接口）
```

注意第一例：分类器同时给出了 `create_activity`（因为含「创建」），但路由**用「如何」信号纠正为 knowledge**——
如果只按意图硬走，就会错误地调创建接口。`evaluate_route()` 用 10 条标注算路由准确率（demo 实测 1.0）。

**决策逻辑**：

```python
def decide(result, threshold=0.6):
    if result["confidence"] < threshold: return {"action": "handoff", ...}
    if "create_activity" in result["intents"]:
        missing = [k for k in REQUIRED_SLOTS if k not in result["slots"]]
        if missing: return {"action": "clarify", "missing": missing, ...}
    return {"action": "execute", ...}
```

## 六、深入分析：设计取舍

**为什么用「信号路由」而不是「纯意图路由」？** 因为分类器（尤其 LLM）会被字面误导：
「如何创建活动」含「创建」，可能被标成 create_activity。若直接按意图调接口，就误操作了。
路由层用**确定性信号**（方法问句、写动作、数据指代）做二次判断，能纠正这类误判——
这叫「分类器给语义，路由给边界」。代价是多一层规则，但换来「不误调接口」的关键保障。

**为什么方法问句优先级最高？** 因为「问怎么做」和「让我做」是本质不同的用户意图，而前者最容易因为含动作词被误判。
把「如何/怎么/为什么/规定/流程」放最高优先级，能兜住最常见的误调接口风险。

**规则 vs LLM，到底用哪个？** 生产常见做法是**规则兜底 + LLM 主判**：LLM 处理开放表达，
规则处理高频确定表达（如「创建」开头直接判创建），既省成本又保稳定。本 demo 的评测显示
LLM 在开放表达上更准（1.0 vs 0.9），但规则零延迟零成本——组合使用才是工程解。

**置信度阈值怎么定？** 没有万能值。原则：**误判代价高就调高阈值**（宁可多转人工），
**体验优先就调低**（宁可多试）。阈值应基于评测集调，而不是拍脑袋。demo 用 0.6 演示。

**多意图怎么处理？** 输出意图数组，下游按优先级或并行处理。硬选一个会丢失用户真实需求
（「查一下再建一个」被识别成纯创建，就漏了查询）。

**为什么强调「不编造」？** 槽位缺失时应留空并触发澄清，而不是让模型猜一个日期。
demo 的 prompt 明确「不要编造用户没说的信息」，`decide` 再兜一层「缺必填就追问」。

## 七、工程实践

- **[teaching-agent/m02](../../projects/teaching-agent/m02_intent_slots.py)** 是本章的 teaching 专用版：
  21 条真实表达回归、`PROMPT_VERSION` 版本管理、`_normalize` 确定性纠偏。本章 demo 是它的通用精简版。
- **版本管理**：改 prompt 必须升版本 + 跑回归（见 m02 的 `PROMPT_VERSION = "intent-v2"`），否则行为悄悄退化。
- **评测驱动**：用标注集算准确率，别凭感觉。demo 的 `EVAL_SET` 是起点，真实项目应扩到几十上百条。
- **练习 1**：给 demo 加一个「向量分类」分支（可用简单字符 bigram 相似度），对比三种方案准确率。
- **练习 2**：把置信度阈值从 0.6 调到 0.8，观察「转人工」变多。
- **练习 3**：构造一条多意图输入（「查一下上周活动，再建一个」），让 `intents` 返回两个。
- **练习 4**：往 `ROUTE_EVAL` 加「取消我的活动」（写动作、非问句）和「取消活动要什么手续？」（方法问句），
  验证前者走 `api_write`、后者走 `knowledge`——体会路由如何区分「做事」与「问信息」。

## 八、本章总结

- **核心知识**：意图/槽位/多意图/置信度；**通道路由（接口 vs 问答）**；三种分类器取舍；归一化 + 三分支决策。
- **必须掌握的原理**：模型负责语义、代码负责边界；LLM 必配归一化；**方法问句优先走问答（防误调接口）**；
  低置信转人工、缺槽位澄清。
- **工程实践能力**：能跑通 demo、解释漂移修复与路由纠正、用标注集评测、做版本管理。
- **联系**：[02-prompt-context](README.md)（prompt 工程）→ 本章（意图+路由）→ [03-tool-use](../03-tool-use/README.md)（调工具）→ [05-planning](../05-planning/README.md)（工作流编排）。

## 九、参考资料

- 本项目：[teaching-agent/m02](../../projects/teaching-agent/m02_intent_slots.py)、[其文档 02-Prompt与上下文工程](../../projects/teaching-agent/docs/02-Prompt与上下文工程.md)
- 本章代码：[intent_recognition.py](../../code/02-prompt-context/intent_recognition.py)
- Prompt 结构化输出：[OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
