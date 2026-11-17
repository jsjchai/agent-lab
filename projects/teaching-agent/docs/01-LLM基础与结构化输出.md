# 01 · LLM 基础与结构化输出

> 对应源文档 §3 · 代码模块 [`m01_structured_output.py`](../m01_structured_output.py) + [`common/llm.py`](../common/llm.py) · 运行：`../../.venv/bin/python m01_structured_output.py`

## 一、这是什么 / 为什么重要

LLM 应用的第一道关口是：**让模型的输出能被程序稳定消费**。模型天然输出自由文本，
而业务系统需要的是结构化、合法、可信赖的数据。源文档 §3 的验收标准说得很直白：

> 输出可稳定解析；字段缺失、类型错误和非法枚举能被程序拦截，**未经校验的模型输出不能进入业务流程**。

在 Teaching 场景里，这意味着模型生成的「活动草稿」必须先变成一个合法的 DTO（活动类型是枚举、
时长在 30–240 分钟、主讲人 1–3 位……），才能交给后续的业务校验和创建流程。否则一个幻觉字段
就可能污染业务表。本模块用 **pydantic** 把这道关口落成代码。

## 二、核心概念详解

### Token 与上下文窗口
模型按 token（文本切分单位）计量输入输出，决定费用与上下文上限。本项目在 `LLM.stats` 里
累计 `prompt_tokens` / `completion_tokens`（mock 用 `len/4` 粗估，真实模式取 API 返回的 usage），
为后续成本核算（[10 分布式可靠性](10-分布式可靠性.md)、[11 模型横向对比](11-模型横向对比.md)）打基础。

### Temperature / Top-p
控制生成随机性。**结构化抽取用低温（0）**，让输出尽量确定；创意生成才用高温。
`LLM.chat(messages, temperature=0.0)` 默认低温，`chat_json` 更是固定 0。

### Structured Output（结构化输出）
让模型按约定 Schema 输出 JSON。有两种约束强度：
- **弱约束**：prompt 里写「只输出 JSON，字段为…」——模型可能不遵守。
- **强约束**：输出后用 Schema 校验，不合格就重试或拒绝。本项目用后者（pydantic）。

### DTO 与 Bean Validation 的 Python 等价
源文档用 Java 的 DTO + `@NotNull/@Size` + Bean Validation。Python 里就是 **pydantic `BaseModel`**：
字段类型、`Field` 约束、`Literal` 枚举、`field_validator` 自定义校验，一一对应。

### Embedding
文本→向量，用于语义检索。本模块不展开，见 [06 RAG](06-RAG与知识问答.md)；`LLM.embed()` 已预留接口。

## 三、代码实现解析

### ActivityDraft：把业务规则写进类型

```python
# m01_structured_output.py
class ActivityDraft(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    activity_type: Literal["教研活动", "培训", "公开课"]
    subject: str = Field(min_length=1)
    grade: Literal["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"] | None = None
    date_text: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    speakers: list[str] = Field(min_length=1, max_length=3)
    duration_minutes: int = Field(ge=30, le=240)

    @field_validator("speakers")
    @classmethod
    def speakers_non_empty(cls, v: list[str]) -> list[str]:
        if any(not s.strip() for s in v):
            raise ValueError("主讲人姓名不能为空")
        return v
```

设计意图：
- `Literal[...]` 把「活动类型/年级」限定为枚举，模型输出「聚餐」直接非法。
- `Field(ge=30, le=240)` 把时长边界写进类型，越界即拦截。
- `speakers` 既限数量（1–3）又用 `field_validator` 禁止空字符串——**两层校验**。
- `grade` 允许 `None`（可选字段），其余必填。

### validate_payload：校验器适配 chat_json

```python
def validate_payload(data: dict) -> str | None:
    try:
        ActivityDraft.model_validate(data)
        return None                       # None = 通过
    except ValidationError as exc:
        return "；".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
```

约定：返回 `None` 表示通过，返回字符串表示错误原因。这个签名是 `LLM.chat_json` 要求的——
错误原因会被回灌给模型做重试提示。

### chat_json：校验 + 重试闭环

`common/llm.py` 的 `chat_json(messages, validate, retries=2)` 流程：
1. 调 `chat` 拿原始输出，`extract_json` 抠出 JSON（兼容 ```json 围栏与前后缀）。
2. 调 `validate`；通过则返回。
3. 不通过则追加一条 user 消息「上一次输出不合格：{原因}。请只输出合法 JSON」，重试。
4. 重试耗尽返回 `{"_error": 原因, "_raw": 原始输出}`，由调用方决定兜底。

**为什么这样写**：小模型一次输出未必合法，把错误原因反馈回去重试，比直接失败更稳；
同时 `stats["errors"]` 记录重试次数，供评测量化格式稳定性。

## 四、工程要点与常见坑

| 现象 | 原因 | 对策 |
|---|---|---|
| 模型输出带 ```json 围栏或解释文字 | 模型习惯加 markdown | `extract_json` 先剥围栏再 `json.loads`，多候选兜底 |
| 字段缺失 / 类型错（时长="九十分钟"） | 模型不守 Schema | pydantic 校验拦截，`chat_json` 重试 |
| 非法枚举（activity_type="聚餐"） | 幻觉 | `Literal` 枚举直接拒绝 |
| 越界数值（duration=999） | 模型无边界感 | `Field(ge/le)` 拦截 |
| 空主讲人 `[""]` | 列表非空但元素空 | `field_validator` 二次校验 |

核心原则：**不要相信模型「会」输出合法 JSON，要用代码确保「只有」合法 JSON 能往下走。**

## 五、验收与测试

`selftest()`（m01）断言：

```python
data = llm.chat_json(messages, validate=validate_payload)
assert "_error" not in data                 # 正常输出通过校验
ActivityDraft.model_validate(data)
assert validate_payload({"title": "x"}) is not None        # 字段缺失被拦截
assert validate_payload({**data, "activity_type": "聚餐"}) is not None  # 非法枚举被拦截
```

`demo()` 还逐一构造 5 类非法输出（字段缺失/类型错误/非法枚举/越界数值/空主讲人）证明全部被拦截，
对应源文档 §3 验收标准。

## 六、与其他模块的关系

- **校验思路贯穿全项目**：[02](02-Prompt与上下文工程.md) 的 `_validate_intent`、[06](06-RAG与知识问答.md) 的引用校验都用同样的「validate 返回 None/原因」契约。
- `chat_json` 是 [02 意图抽取](02-Prompt与上下文工程.md)、[06 RAG 回答](06-RAG与知识问答.md) 的底层。
- `ActivityDraft` 的字段与 [04 工具](04-工具调用与业务工具设计.md) 的 `build_activity_draft`、`common/business.py` 的 `validate_draft` 对齐。
- `LLM.stats` 的 token 计数被 [11 模型对比](11-模型横向对比.md) 复用。

## 七、动手练习与延伸

1. 给 `ActivityDraft` 加一个非法枚举值（如 `activity_type="聚会"`），跑 `demo()` 看是否被拦截。
2. 把 `duration_minutes` 上限改成 120，构造 150 分钟的草稿，观察校验报错信息。
3. 接真实模型（`TEACHING_LLM=openai` + Ollama），跑 `chat_json` 观察 `stats["errors"]`（重试次数），对比 mock 的 0 重试。

## 参考

- 源文档 §3「LLM 基础」
- [Pydantic 文档](https://docs.pydantic.dev/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- 项目内：[`common/llm.py`](../common/llm.py)、[02 Prompt 与上下文工程](02-Prompt与上下文工程.md)
