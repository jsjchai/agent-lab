#!/usr/bin/env python3
"""jev_decision_demo · JEV / System One 决策模型的接口契约与路由集成
—— docs/02-prompt-context/05-jev-system-one-decision-models.md 代码锚点。

⚠️ 重要说明：本文件**不是** TypeSafe JEV 的调用实现，也不会联网。
它用本地桩（Stub）模拟「System One 决策模型」的**接口契约**，用来讲清三件事：
1. 输入是「程序状态 + 类型化问题」，不是一段自由文本；
2. 输出是「类型安全 + 带校准概率」的结构化答案，代码可直接分支；
3. 拿到答案后必须校验（键匹配、选项合法、概率和≈1、argmax 一致），失败要能识别。

三类问题（按其社区文档的常见分法）：
- Noul：是/否 判断，返回概率；
- Choice：从给定选项里选，返回各选项概率；
- Score：按标准打分，返回各档概率。

真实接法见文档 §6：POST /api/v1/decide（具体字段以官方文档为准），
本 demo 只用同名概念，不声称与真实 API 完全一致。

运行（离线）：../../.venv/bin/python jev_decision_demo.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


class InvalidAnswer(Exception):
    """答案不满足类型/概率约束（对应真实 SDK 的 InvalidAnswers 类错误）。"""


@dataclass
class Noul:
    key: str
    question: str


@dataclass
class Choice:
    key: str
    question: str
    options: list[str]
    # 可选：给每个选项配关键词，供本地桩打分（真实模型不需要，它自己会判）
    hints: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Score:
    key: str
    question: str
    levels: list[str]


@dataclass
class Answer:
    key: str
    kind: str
    value: str                  # Noul: "yes"/"no"；Choice/Score: 选中的选项
    probabilities: dict[str, float]
    model: str = "stub-jev-0.0"

    def confidence(self) -> float:
        return self.probabilities[self.value]


# --------------------------------------------------------------------------- 本地桩
class LocalStubModel:
    """模拟 System One 的并行决策：一次返回所有问题的答案与概率。

    这里用确定性规则打分（真实模型是训练出来的），只为演示接口形状。
    """

    def __init__(self, model_id: str = "stub-jev-0.0"):
        self.model_id = model_id
        self.calls = 0

    def _softmax(self, scores: dict[str, float]) -> dict[str, float]:
        import math
        mx = max(scores.values())
        exp = {k: math.exp(v - mx) for k, v in scores.items()}
        z = sum(exp.values())
        return {k: round(v / z, 2) for k, v in exp.items()}

    def decide(self, state: str, questions: list) -> list[Answer]:
        self.calls += 1
        out = []
        for q in questions:
            if isinstance(q, Noul):
                hit = any(w in state for w in ("删除", "转账", "生产", "对外发布"))
                probs = {"yes": 0.86, "no": 0.14} if hit else {"yes": 0.09, "no": 0.91}
                value = max(probs, key=probs.get)
                out.append(Answer(q.key, "noul", value, probs, self.model_id))
            elif isinstance(q, Choice):
                # 关键词打分 → softmax，模拟「按选项给概率」
                scores = {}
                for opt in q.options:
                    kws = q.hints.get(opt, [])
                    scores[opt] = 2.0 * sum(1 for k in kws if k in state)
                probs = self._softmax(scores)
                value = max(probs, key=probs.get)
                out.append(Answer(q.key, "choice", value, probs, self.model_id))
            elif isinstance(q, Score):
                probs = {"1": 0.5, "2": 0.2, "3": 0.15, "4": 0.1, "5": 0.05}
                probs = {k: v for k, v in probs.items() if k in q.levels}
                z = sum(probs.values()) or 1.0
                probs = {k: round(v / z, 2) for k, v in probs.items()}
                value = max(probs, key=probs.get)
                out.append(Answer(q.key, "score", value, probs, self.model_id))
            else:
                raise TypeError(f"未知问题类型: {q}")
        return out


# --------------------------------------------------------------------------- 答案校验
def validate(questions: list, answers: list[Answer], tol: float = 0.02) -> list[str]:
    """类型安全校验：键匹配、必答项齐全、选项合法、概率范围与和、argmax 一致。"""
    problems = []
    by_key = {a.key: a for a in answers}
    for q in questions:
        a = by_key.get(q.key)
        if a is None:
            problems.append(f"缺少答案: {q.key}")
            continue
        if isinstance(q, Choice):
            if set(a.probabilities) != set(q.options):
                problems.append(f"{q.key}: 选项集合不一致")
        if isinstance(q, Score):
            if set(a.probabilities) != set(q.levels):
                problems.append(f"{q.key}: 评分档位不一致")
        if isinstance(q, Noul):
            if set(a.probabilities) != {"yes", "no"}:
                problems.append(f"{q.key}: Noul 概率键应为 yes/no")
        if a.value not in a.probabilities:
            problems.append(f"{q.key}: 选中的值不在概率表中")
            continue
        total = sum(a.probabilities.values())
        if abs(total - 1.0) > tol:
            problems.append(f"{q.key}: 概率和 {total:.2f} 偏离 1")
        for p in a.probabilities.values():
            if not 0.0 <= p <= 1.0:
                problems.append(f"{q.key}: 概率越界 {p}")
        if max(a.probabilities, key=a.probabilities.get) != a.value:
            problems.append(f"{q.key}: 选中值不是 argmax（概率不一致）")
    return problems


# --------------------------------------------------------------------------- 用例
def route_with_decision_model(state: str) -> str:
    """用例 1：把路由做成一个 Choice 问题（对比 03 章的规则/向量/LLM 路由）。"""
    model = LocalStubModel()
    q = Choice("route", "用户想做什么？", ["query_schedule", "create_session", "knowledge_qa", "chat"],
               hints={"query_schedule": ["查一下", "查询", "看看", "排期", "列表"],
                      "create_session": ["安排", "创建", "组织", "举办"],
                      "knowledge_qa": ["如何", "怎么", "要求", "规定"]})
    answers = model.decide(state, [q])
    problems = validate([q], answers)
    if problems:
        raise InvalidAnswer("; ".join(problems))
    a = answers[0]
    if a.confidence() < 0.6:
        return f"低于阈值 → 澄清（{a.value} {a.confidence()}）"
    return a.value


def guard_with_decision_model(state: str) -> str:
    """用例 2：把「是否高风险」做成 Noul，用概率做 guardrail。"""
    model = LocalStubModel()
    q = Noul("high_risk", "这个操作是否高风险（删除/转账/对外发布）？")
    a = model.decide(state, [q])[0]
    return f"high_risk={a.value} p={a.confidence()}"


def score_with_decision_model(state: str) -> str:
    """用例 3：把「回复质量」做成 Score。"""
    model = LocalStubModel()
    q = Score("quality", "这条回复质量如何？", ["1", "2", "3", "4", "5"])
    a = model.decide(state, [q])[0]
    return f"score={a.value} p={a.confidence()}"


# --------------------------------------------------------------------------- 演示 / 自检
def demo() -> None:
    print("【jev_decision_demo】JEV / System One 接口契约（本地桩，非真实 API）")
    state = "帮我安排下周三心内科的教学查房，带教老师张三"

    print("\n  ① 路由做成 Choice 问题")
    print("   state:", state)
    print("   answer:", route_with_decision_model(state))

    print("\n  ② 高风险判断做成 Noul")
    print("   answer:", guard_with_decision_model("请删除所有历史活动并生成对外发布稿"))

    print("\n  ③ 质量评分做成 Score")
    print("   answer:", score_with_decision_model("按照规则产出了完整草稿"))

    print("\n  ④ 一次并行问多个问题（System One 的关键差异）")
    model = LocalStubModel()
    qs = [
        Choice("route", "用户想做什么？", ["query_schedule", "create_session", "knowledge_qa"],
               hints={"query_schedule": ["查一下", "查询", "看看", "排期", "列表"],
                      "create_session": ["安排", "创建", "组织"],
                      "knowledge_qa": ["如何", "怎么", "要求"]}),
        Noul("high_risk", "是否高风险？"),
        Score("quality", "当前信息完整度？", ["1", "2", "3", "4", "5"]),
    ]
    answers = model.decide(state, qs)
    for a in answers:
        print(f"   {a.key:<10} {a.value:<16} p={a.confidence():.2f}  model={a.model}")
    print("   校验问题:", validate(qs, answers) or "无")

    print("\n  ⑤ 校验能抓住坏答案（模拟类型/概率异常）")
    bad = Answer("route", "choice", "create_session", {"query_schedule": 0.7, "create_session": 0.5})
    print("   问题:", validate([Choice("route", "x", ["query_schedule", "create_session"])], [bad]))

    print("\n  结论：Decision Model 的价值是把「判断」变成类型安全、带概率的函数调用；")
    print("        代价是它只做判断，不生成内容——与 LLM 分工，而不是替代。")


def selftest() -> None:
    model = LocalStubModel()
    state = "帮我安排下周三心内科的教学查房"
    q = Choice("route", "用户想做什么？", ["query_schedule", "create_session", "knowledge_qa"],
               hints={"query_schedule": ["查一下", "查询", "看看", "排期", "列表"],
                      "create_session": ["安排", "创建", "组织"],
                      "knowledge_qa": ["如何", "怎么", "要求"]})
    answers = model.decide(state, [q])
    assert len(answers) == 1 and answers[0].key == "route"
    assert validate([q], answers) == []                    # 合法答案无问题
    # 三个用例都能跑
    assert route_with_decision_model(state) in ("create_session", "澄清", "query_schedule", "knowledge_qa")
    assert "high_risk=" in guard_with_decision_model("删除所有记录")
    assert "score=" in score_with_decision_model("good")
    # 并行多问题
    qs = [q, Noul("risk", "是否高风险？"), Score("q", "质量？", ["1", "2"])]
    ans = model.decide(state, qs)
    assert len(ans) == 3 and validate(qs, ans) == []
    # 校验能发现：缺答案、概率和不为 1、argmax 不一致、选项不一致
    assert any("缺少答案" in p for p in validate(qs, [ans[0]]))
    bad_sum = Answer("route", "choice", "query_schedule", {"query_schedule": 0.9, "create_session": 0.5})
    assert any("偏离 1" in p for p in validate([q], [bad_sum]))
    bad_argmax = Answer("route", "choice", "create_session", {"query_schedule": 0.9, "create_session": 0.1})
    assert any("argmax" in p for p in validate([q], [bad_argmax]))
    bad_opts = Answer("route", "choice", "x", {"x": 1.0})
    assert any("选项集合不一致" in p for p in validate([q], [bad_opts]))
    # 确定性：同输入同输出
    assert model.decide(state, [q])[0].value == model.decide(state, [q])[0].value


if __name__ == "__main__":
    demo()
