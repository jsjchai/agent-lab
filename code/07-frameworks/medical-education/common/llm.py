"""统一 LLM 适配层 —— 两个医疗教学 Agent 例子共用。

两种后端，靠环境变量切换：

    AGENT_LLM=mock    # 默认。完全离线、结果确定，用于演示和测试
    AGENT_LLM=openai  # 任何 OpenAI 兼容接口：OpenAI / DeepSeek / Qwen / vLLM / Ollama

真实模式需要的变量：

    OPENAI_API_KEY=sk-...
    AGENT_MODEL=gpt-4o-mini            # 或 deepseek-chat / qwen-plus ...
    OPENAI_BASE_URL=https://...        # 可选，本地模型或第三方网关时填

为什么要这个适配层：
医疗教学内容的生成质量依赖真实模型，但*流程*（状态机、循环、多角色协作）
不依赖模型。把 LLM 抽成一层，流程就可以在离线模式下被复现和测试。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_MODEL = "gpt-4o-mini"


# --------------------------------------------------------------------------- 配置
def current_mode() -> str:
    """返回当前后端：mock / openai。"""
    return os.getenv("AGENT_LLM", "mock").strip().lower()


def model_name() -> str:
    return os.getenv("AGENT_MODEL", DEFAULT_MODEL)


def is_small_model() -> bool:
    """判断当前是不是"小模型"档位。

    可以用 AGENT_PROFILE=small|large 强制指定；默认按模型名里的参数规模猜。
    小模型（7B/8B 级）在**长指令**和**格式稳定性**上明显更差，需要更硬的约束。
    """
    forced = os.getenv("AGENT_PROFILE", "auto").strip().lower()
    if forced in {"small", "large"}:
        return forced == "small"
    name = model_name().lower()
    if re.search(r"(?:^|[^0-9])(?:[1-9]|1[0-4])b(?:[^0-9]|$)", name):
        return True
    return any(tag in name for tag in ("mini", "tiny", "small", "flash", "lite"))


def small_only(rule: str) -> str:
    """只在小模型档位追加的硬约束（大模型不需要，加了反而啰嗦）。"""
    return f"\n\n硬约束：{rule}" if is_small_model() else ""


def describe() -> str:
    """给 CLI 打印用的一行环境说明。"""
    if current_mode() == "mock":
        return "LLM 后端：mock（离线，无需 API key）"
    base = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    tier = "小模型档位：已启用硬约束" if is_small_model() else "大模型档位"
    return f"LLM 后端：openai（model={model_name()}, base_url={base}，{tier}）"


# --------------------------------------------------------------------------- 工具
def extract_json(text: str) -> dict[str, Any]:
    """从模型输出里抠出 JSON。

    真实模型经常会加 ```json 围栏或前后缀说明，这里做兼容；
    解析失败时返回带原始文本的兜底结构，让上层的路由逻辑不至于崩。
    """
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    for candidate in (cleaned, cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return {"score": 0, "verdict": "parse_error", "issues": ["模型输出不是合法 JSON"], "raw": text}


# --------------------------------------------------------------------------- mock 素材
_TOPIC_RE = re.compile(r"教学主题[：:]\s*(.+)")
_LEVEL_RE = re.compile(r"学习者[：:]\s*(.+)")


def _pick(pattern: re.Pattern[str], text: str, default: str) -> str:
    m = pattern.search(text)
    return m.group(1).strip().splitlines()[0] if m else default


_REVIEW_CALLS = 0


def _scene_plan(user: str) -> str:
    topic = _pick(_TOPIC_RE, user, "社区获得性肺炎（CAP）")
    level = _pick(_LEVEL_RE, user, "住院医师规范化培训第一年（R1）")
    return f"""## 教学目标（{topic}）

学习者画像：{level}

1. **知识（Bloom：理解）**：能复述{topic}的诊断依据与病情分层标准，并解释每一条的临床意义。
2. **技能（Bloom：应用）**：能对给定病例独立完成初始评估，选择检查与治疗路径。
3. **素养（Bloom：分析）**：能在病情与预期不符时，主动提出鉴别诊断并说明调整理由。

## 教学安排建议
- 时长 90 分钟：课前预习 15 分钟 + 床旁/病例讨论 60 分钟 + 复盘与反馈 15 分钟
- 组织形式：2 人一组，先独立书写评估单，再对照标准答案讨论
- 评价方式：Mini-CEX（重点：病史采集、诊断推理、沟通）

## 难点预判
- 分层工具（如严重程度评分）容易背下来但不会用，需要设计"算错会怎样"的追问。
"""


def _scene_case(user: str) -> str:
    return """## 教学病例：反复发热待查（模拟病例，非真实患者）

**主诉**：发热伴咳嗽、咳痰 5 天，加重 1 天。

**现病史**：5 天前受凉后出现发热，最高 38.9℃，伴咳黄痰、右侧胸痛，活动后气促。
自服"感冒药"无好转。今晨体温 39.2℃，精神差，家属送来就诊。病程中无咯血、无夜间盗汗。

**既往史**：2 型糖尿病 8 年，口服二甲双胍，血糖控制一般（HbA1c 8.1%）。
否认吸烟、饮酒。否认近期外地旅行及结核接触史。

**查体**：T 39.2℃，P 112 次/分，R 26 次/分，BP 96/60 mmHg，SpO₂ 92%（未吸氧）。
神清，急性病容。右下肺呼吸音减低，可闻及湿性啰音。心律齐，未闻及杂音。双下肢无水肿。

**辅助检查**：WBC 15.8×10⁹/L，中性粒细胞 88%；CRP 156 mg/L；PCT 1.2 ng/mL。
胸片：右下肺大片状实变影，伴少量胸腔积液。血气（未吸氧）：pH 7.45，PaO₂ 58 mmHg，PaCO₂ 32 mmHg。

**教学提示**：本病例资料完整度足以完成初始评估与分层，但故意缺少部分信息，
请学习者自行判断"还缺什么、为什么缺、缺了会影响哪个决策"。
"""


def _scene_questions(user: str) -> str:
    return """## 分层问题

**Q1（记忆/理解）** 该患者符合社区获得性肺炎的哪些诊断依据？请逐条对应病例信息。
- 参考答案：急性起病 + 发热咳嗽咳痰 + 肺部湿啰音 + 白细胞与炎症指标升高 + 胸片新发浸润影。
- 评分点：能说出 5 条中的 4 条即达标；能区分"诊断依据"与"病情严重程度依据"加分。

**Q2（应用）** 请计算该患者的 CURB-65 评分，并据此说明门诊、住院还是 ICU？
- 参考答案：意识清（0）+ 尿素氮（未查，需补）= 不可完整计算；按已有条目：呼吸 26 次/分（0）、
  BP 96/60（收缩压 <90 记 1 分？96 不满足）、年龄未知。**关键考点是识别"信息不足"并要求补充**。
  按氧合与血压趋势、糖尿病史，倾向住院治疗，需监测是否达重症标准。
- 评分点：是否主动指出尿素氮、年龄缺失；是否给出"先住院观察再评估"的合理路径。

**Q3（分析/评价）** 若经验性抗感染 48~72 小时后体温不降，你的下一步思路是什么？
- 参考答案：① 复核诊断（是否非感染性疾病、特殊病原体、并发症如脓胸）；② 复核标本与药敏；
  ③ 评估是否有引流指征；④ 调整方案前先明确"无效"的定义（临床稳定标准）。
- 评分点：能按"诊断—病原—并发症—治疗"顺序排查，而不是直接升级抗生素。
"""


def _scene_review(user: str) -> str:
    """第一轮故意不通过，用来演示 LangGraph 的条件边 + 回环。"""
    global _REVIEW_CALLS
    _REVIEW_CALLS += 1
    if _REVIEW_CALLS == 1:
        return json.dumps(
            {
                "score": 78,
                "verdict": "needs_revision",
                "issues": [
                    "病例缺少鉴别诊断的提示信息（结核、肺栓塞、心衰）",
                    "Q2 的参考答案自相矛盾：先说无法计算，又直接给出住院结论，缺中间推理",
                    "缺少形成性评价量规（谁在什么时点、按什么标准给反馈）",
                ],
                "suggestion": "补充鉴别诊断线索，重写 Q2 的推理链，并为每个问题加 0/1/2 三档评分描述。",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "score": 88,
            "verdict": "pass",
            "issues": [],
            "suggestion": "可用于床旁教学。建议课前把 Q2 的「信息不足」设计成显式停顿点。",
        },
        ensure_ascii=False,
    )


def _scene_revise(user: str) -> str:
    return """## 教学病例（修订版）

在初版基础上补充三处：

1. **鉴别诊断线索**：补充"近 3 个月体重下降 4 kg""夜间盗汗偶有"，提示需与肺结核鉴别；
   补充"长途乘车后右下肢肿胀"阴性史，用于排除肺栓塞；补充 BNP 与心脏超声结果正常，排除心衰。
2. **Q2 推理链重写**：先列出 CURB-65 五个条目 → 标出缺失项（年龄、尿素氮）→ 说明"信息不足时
   的正确动作是补充资料，而非猜测" → 再给出"按现有资料倾向住院并密切监测"的临时决策及其依据。
3. **评分量规**：每题给出 0/1/2 三档描述——0 分=结论错误或无依据；1 分=结论对但推理跳跃；
   2 分=结论与推理均完整，且主动指出信息缺口。

修订说明：上述改动同时回应了评审提出的三条意见。
"""


# --------------------------------------------------------------------------- CrewAI 用的角色化 mock
# 任务描述里会带上显式的环节标记（如「【环节】汇总」）。
# 为什么需要它：CrewAI 的 context= 会把前序任务的产出一并拼进 prompt，
# 于是「汇总」任务的 prompt 里同样会出现「考核」「评价」等词，
# 只按关键词路由会认错角色。让标记优先、关键词只做兜底，路由才稳定。
_CREW_STAGE_RE = re.compile(r"【环节】\s*(设计|临床|考核|汇总)")
_CREW_DEFAULT_TOPIC = "急性胸痛"


def _crew_stage(prompt_text: str) -> str | None:
    """从 prompt 中取出任务环节标记；取不到返回 None。"""
    match = _CREW_STAGE_RE.search(prompt_text)
    return match.group(1) if match else None


def _crew_reply(prompt_text: str) -> str:
    """按 Agent 角色返回内容；CrewAI 最终只取 Final Answer 之后的部分。

    路由优先级：任务描述里的「【环节】X」标记 > 关键词兜底。
    """
    stage = _crew_stage(prompt_text)
    # 有标记时以标记为准；没有标记（旧调用方式）再退回关键词判断。
    is_assess = stage == "考核" or (stage is None and ("考核" in prompt_text or "评价" in prompt_text))
    is_clinic = stage == "临床" or (stage is None and ("临床" in prompt_text or "心内" in prompt_text))
    is_summary = stage == "汇总" or (stage is None and ("汇总" in prompt_text or "整合" in prompt_text))

    if is_assess:
        body = """## 考核与评价方案（Mini-CEX + 病例题）

**Mini-CEX 评分表（7 项，每项 1-9 分）**
| 维度 | 观察要点 | 不达标（1-3） | 达标（4-6） | 优秀（7-9） |
|---|---|---|---|---|
| 病史采集 | 是否问到胸痛特征、诱因、伴随症状 | 漏问关键项 | 基本完整 | 有条理且能追问 |
| 体格检查 | 心肺查体顺序与手法 | 顺序混乱 | 规范 | 规范且能解释阳性体征 |
| 诊断推理 | 能否列出鉴别诊断并排序 | 只给一个诊断 | 列出 3 个 | 能按概率与危险度排序 |
| 处置计划 | 检查与治疗的优先级 | 无优先顺序 | 合理 | 能说明"先做什么、为什么" |
| 沟通 | 向患者解释病情 | 术语堆砌 | 通俗 | 兼顾情绪与知情 |
| 专业素养 | 人文关怀、隐私保护 | 缺失 | 基本 | 主动体现 |
| 整体表现 | 综合判断 | — | — | — |

**病例题（3 道，含评分要点）**
1. 胸痛 20 分钟、心电图 ST 段抬高，最先做的三件事是什么？（要点：监护/吸氧/建立静脉通路、抗血小板、
   启动导管室；按"时间就是心肌"排序）
2. 若患者主诉"撕裂样"胸痛并向背部放射，你的鉴别诊断与首选检查？（要点：主动脉夹层 → CTA）
3. 如何在 3 分钟内完成一次让患者听懂的风险沟通？（要点：结构化、共情、下一步明确）

**反馈机制**：当场口头反馈 2 分钟 + 24 小时内书面反馈；每轮记录分数变化趋势。
"""
    elif is_clinic:
        body = """## 临床要点与常见误区

**必须掌握的三条主线**
1. 时间线：症状发作 → 首份心电图 → 再灌注，每一环的时间都决定预后。
2. 危险分层：STEMI / NSTEMI / 不稳定型心绞痛的处理路径不同，先分层再治疗。
3. 鉴别诊断：主动脉夹层、肺栓塞、气胸、心包炎、食管痉挛——"胸痛五项"要能脱口而出。

**学员最常见的五个误区**
- 只看心电图不看症状演变，把"正常心电图"当成"排除心梗"。
- 忘记询问抗凝/出血史就给药。
- 把"胸痛缓解"当成"病情稳定"，忽略再灌注时间窗。
- 忽略右室梗死导致的下壁心梗低血压（硝酸酯类禁忌）。
- 交班时只报数据，不报"我担心什么、下一步计划"。

**教学提问设计**
- "如果这份心电图是 30 分钟前的，你的处理会变吗？"
- "患者说疼得好点了，你的处置顺序会调整吗？为什么？"
"""
    elif is_summary:
        body = """## 教学活动方案汇总

**活动名称**：急性胸痛 60 分钟教学查房
**对象**：内科住院医师 R1-R2（6-8 人）
**目标**：完成一次结构化胸痛评估，能区分 STEMI/NSTEMI/夹层并说明处置优先级

**流程**
| 时间 | 环节 | 形式 | 产出 |
|---|---|---|---|
| 0-5 min | 导入：一个真实主诉 | 提问 | 学员列出"最先想到的 3 个诊断" |
| 5-25 min | 床旁/病例评估 | 2 人一组 | 评估单（病史+查体+首份检查） |
| 25-40 min | 诊断推理讨论 | 白板推演 | 鉴别诊断排序 + 依据 |
| 40-55 min | 处置与沟通演练 | 角色扮演 | 3 分钟风险沟通 |
| 55-60 min | 反馈与作业 | Mini-CEX | 每人 1 条改进点 |

**评价**：Mini-CEX + 3 道病例题；形成性反馈当日完成。
**风险提示**：涉及真实病例时须去标识化；模拟演练需声明"非真实抢救"。
"""
    else:
        body = """## 教学目标与教学流程设计

**教学目标（Bloom 分层）**
1. 理解：能说出急性胸痛的五大高危病因及其鉴别要点。
2. 应用：能对模拟病例完成 10 分钟内结构化评估并给出优先级。
3. 分析：能根据病情变化调整诊断假设并说明理由。

**时间分配表（60 分钟）**
| 时间 | 环节 | 教师动作 | 学员动作 |
|---|---|---|---|
| 0-5 | 情境导入 | 给出主诉，不给诊断 | 写出 3 个最可能诊断 |
| 5-20 | 资料采集 | 逐条释放病史/查体/心电图 | 分组填写评估单 |
| 20-35 | 推理讨论 | 追问"为什么" | 排序并辩护 |
| 35-50 | 处置演练 | 设置病情变化 | 调整方案 |
| 50-60 | 反馈 | Mini-CEX 点评 | 自评 + 互评 |

**设计原则**：先让学员犯错再讲解；每 15 分钟设置一次"信息不全"的停顿点，训练主动提问。
"""
    # 让 mock 也跟随 --topic / --level 变化，而不是永远输出"急性胸痛"，
    # 这样切换主题时能肉眼确认参数真的传到了 Agent 的 prompt 里。
    topic = _pick(_TOPIC_RE, prompt_text, _CREW_DEFAULT_TOPIC)
    body = body.replace(_CREW_DEFAULT_TOPIC, topic)
    # 主题不是胸痛时，把正文里残留的"胸痛"也换成对应症状词。
    # 注意：mock 的素材本身是按胸痛写的，这里只做词级替换模拟"模型跟随输入"，
    # 具体医学细节的准确性请用 AGENT_LLM=openai 看真实模型输出。
    symptom = topic.replace("急性", "").split("（")[0].split("(")[0].strip()
    if symptom and symptom != "胸痛":
        body = body.replace("胸痛", symptom)
    level = _pick(_LEVEL_RE, prompt_text, "内科住院医师（R1-R2）")
    body = body.replace("内科住院医师 R1-R2", level)
    return f"Thought: 我已根据角色职责整理好本环节内容。\nFinal Answer: {body}"


# --------------------------------------------------------------------------- 对外接口
class LLMClient:
    """脚本里直接用这个：`LLMClient().complete(scene, system, user)`。"""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or current_mode()).lower()
        self._client = None
        if self.mode not in {"mock", "openai"}:
            raise ValueError(f"未知 AGENT_LLM={self.mode!r}，只支持 mock / openai")

    # -- 真实后端
    def _openai(self, system: str, user: str, temperature: float, max_tokens: int | None = None) -> str:
        if self._client is None:
            from openai import OpenAI  # 延迟导入：mock 模式不需要这个包

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "AGENT_LLM=openai 但没有设置 OPENAI_API_KEY。"
                    "想离线运行请 export AGENT_LLM=mock"
                )
            self._client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)
        # 小模型容易啰嗦，默认压一下输出长度；大模型不设限
        if max_tokens is None and is_small_model():
            max_tokens = 900
        resp = self._client.chat.completions.create(
            model=model_name(),
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    # -- 统一入口
    def complete(
        self,
        scene: str,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """scene 是给 mock 用的路由键，真实模型会忽略它。"""
        if self.mode == "openai":
            return self._openai(system, user, temperature, max_tokens)
        handler = _SCENES.get(scene)
        if handler is None:
            raise KeyError(f"mock 模式没有定义 scene={scene!r}，可选：{sorted(_SCENES)}")
        return handler(user)

    # -- 结构化输出：小模型最容易在这里翻车，所以带校验和重试
    def complete_json(
        self,
        scene: str,
        system: str,
        user: str,
        validate,
        retries: int = 2,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """要求模型输出 JSON，并用 validate 校验；不合格就把错误回灌给它重试。

        validate(data) -> None 表示通过，返回字符串表示不合格原因。
        重试仍失败时返回 {"_error": 原因, "_raw": 原始输出}，让调用方决定怎么兜底。
        """
        raw = ""
        reason = "未知错误"
        for attempt in range(retries + 1):
            feedback = "" if attempt == 0 else (
                f"\n\n上一次输出不合格，原因：{reason}\n"
                "请只输出一个合法 JSON 对象，不要解释、不要 Markdown 代码块。"
            )
            raw = self.complete(scene, system, user + feedback, temperature=temperature)
            data = extract_json(raw)
            reason = validate(data) or ""
            if not reason:
                return data
        return {"_error": reason, "_raw": raw}


_SCENES = {
    "plan": _scene_plan,
    "case": _scene_case,
    "questions": _scene_questions,
    "review": _scene_review,
    "revise": _scene_revise,
}


def make_crewai_llm():
    """CrewAI 需要它自己的 LLM 对象；mock 模式返回一个确定性替身。"""
    if current_mode() == "mock":
        from crewai.llms.base_llm import BaseLLM

        class MockCrewLLM(BaseLLM):  # type: ignore[misc]
            def __init__(self) -> None:
                super().__init__(model="mock/medical-education")

            def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):  # type: ignore[override]
                text = "\n".join(
                    str(m.get("content", "")) if isinstance(m, dict) else str(m) for m in messages
                )
                return _crew_reply(text)

            def supports_function_calling(self) -> bool:
                return False

            def supports_stop_words(self) -> bool:
                return True

            def get_input_tokens_count(self, messages, tools=None, response_model=None) -> int:
                """覆盖基类的估算方法。

                基类实现每次都会打一条 "approximate token count" 警告，四个任务跑下来
                控制台全是噪音。mock 没有 tokenizer，用字符数/4 粗估即可。
                """
                if isinstance(messages, str):
                    text = messages
                else:
                    text = "".join(
                        str(m.get("content", "")) if isinstance(m, dict) else str(m)
                        for m in messages
                    )
                return max(1, len(text) // 4)

        return MockCrewLLM()

    from crewai import LLM

    # LiteLLM 需要 "provider/model" 形式。接本地 Ollama / vLLM 时模型名通常没有前缀，
    # 这类 OpenAI 兼容服务统一走 openai/ 通道。
    model = model_name()
    if "/" not in model:
        model = f"openai/{model}"

    return LLM(
        model=model,
        temperature=0.4,
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        api_key=os.getenv("OPENAI_API_KEY") or "not-needed",
        timeout=180,  # 本地小模型首 token 可能较慢
    )


if __name__ == "__main__":
    # 自检：python -m common.llm
    print(describe())
    client = LLMClient()
    print(client.complete("plan", "你是教学设计师", "教学主题：急性胸痛\n学习者：R1")[:200])
