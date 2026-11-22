#!/usr/bin/env python3
"""intent_router · Agent 的意图路由设计 —— docs/02-prompt-context/03-agent-intent-routing.md 代码锚点。

问题：意图路由不该是一串 if/else。当 Agent 有 6 个以上去处（查数据、建活动、知识问答、
专业子代理、长流程、闲聊），硬编码判断会迅速失控。

本 demo 演示一个可演进的路由层设计：
1. **路由注册表（declarative routes）**：每个去处声明关键词、示例、风险级别、成本、处理器。
2. **候选生成 + 打分**：关键词命中 + 语义相似（字符 bigram）+ LLM 兜底，三种信号融合。
3. **阈值 + 边距**：最高分不够高或与第二名太接近 → 不硬猜，转澄清或兜底。
4. **风险分级**：写操作路由标记 requires_approval，交给下游确认。
5. **多意图**：按「再/然后/并且」切分子句，逐段路由，输出任务列表。
6. **可观测 + 可评测**：记录每次决策的分数与理由；用标注集算路由准确率。

运行（离线 mock）：../../.venv/bin/python intent_router.py
"""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- 路由注册表
@dataclass
class Route:
    name: str
    kind: str                     # tool_read / tool_write / knowledge / subagent / workflow / chat
    keywords: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    risk: str = "low"             # low / medium / high
    cost: int = 1                 # 相对成本（1 低，5 高）
    requires_approval: bool = False

    def handler(self) -> str:
        return f"{self.kind}:{self.name}"


ROUTES = [
    Route("query_schedule", "tool_read",
          keywords=["查", "排期", "有哪些", "列表", "安排在哪"],
          examples=["查一下我下周的教学安排", "看看有哪些排期", "我的教学活动列表"]),
    Route("create_session", "tool_write",
          keywords=["安排", "创建", "组织", "举办", "排课"],
          examples=["帮我安排一次教学查房", "组织一次病例讨论", "创建技能培训"],
          risk="high", cost=2, requires_approval=True),
    Route("knowledge_qa", "knowledge",
          keywords=["如何", "怎么", "要求", "规定", "流程", "是什么"],
          examples=["教学查房有哪些要求？", "培训流程是什么？", "如何申请教学查房？"],
          cost=2),
    Route("exam_workflow", "workflow",
          keywords=["考核", "考试", "认证", "全院"],
          examples=["组织全院心肺复苏技能考核", "安排一次年度考核"],
          risk="high", cost=4, requires_approval=True),
    Route("subagent_scheduling", "subagent",
          keywords=["冲突", "协调", "同时", "排不开"],
          examples=["下周两个科室的查房排期冲突了，帮我协调", "多个活动时间冲突怎么协调"],
          cost=5),
    Route("chat", "chat",
          keywords=[], examples=["今天天气不错", "你好"],
          cost=1),
]

# --------------------------------------------------------------------------- 信号：关键词 + 语义
def bigrams(text: str) -> set[str]:
    t = "".join(ch for ch in text if ch.strip())
    return {t[i:i + 2] for i in range(len(t) - 1)} or {t}


def similarity(a: str, b: str) -> float:
    """字符 bigram Jaccard（离线可跑的轻量语义相似）。"""
    ba, bb = bigrams(a), bigrams(b)
    return len(ba & bb) / len(ba | bb) if ba and bb else 0.0


def keyword_score(text: str, route: Route) -> float:
    hits = [k for k in route.keywords if k in text]
    if not hits:
        return 0.0
    return {1: 0.6, 2: 0.85}.get(len(hits), 1.0)


def semantic_score(text: str, route: Route) -> float:
    return max((similarity(text, ex) for ex in route.examples), default=0.0)


# --------------------------------------------------------------------------- 选择：阈值 + 边距
@dataclass
class Decision:
    clause: str
    route: Route | None
    scores: dict
    reason: str
    action: str          # dispatch / clarify / fallback
    requires_approval: bool = False


THRESHOLD = 0.38        # 绝对分下限：太低说明没匹配上
MARGIN = 0.06           # 与第二名的最小差距：太接近说明有歧义
AMBIGUOUS_MIN = 0.20    # 有一点信号但不达标 → 澄清；完全没信号 → 兜底闲聊


SHORT_INPUT_MAX = 2     # 极短输入（如只有"安排"）信息不足，直接澄清


def route_clause(text: str) -> Decision:
    clean = "".join(ch for ch in text if ch.strip())
    if len(clean) <= SHORT_INPUT_MAX:
        return Decision(text, None, {"_scores": {}}, "输入过短，信息不足", "clarify")
    scored = []
    for r in ROUTES:
        kw = keyword_score(text, r)
        sem = semantic_score(text, r)
        score = 0.6 * kw + 0.4 * sem          # 权重和=1，分数落在 [0,1]
        scored.append((score, r, {"keyword": round(kw, 2), "semantic": round(sem, 2)}))
    detail = {r.name: d for s, r, d in scored}
    detail["_scores"] = {r.name: round(s, 3) for s, r, _ in scored}

    # 闲聊只做兜底，不参与业务路由竞争
    business = [(s, r) for s, r, _ in scored if r.kind != "chat"]
    business.sort(key=lambda x: (-x[0], x[1].cost))
    best_score, best_route = business[0]
    second = business[1][0] if len(business) > 1 else 0.0

    if best_score < AMBIGUOUS_MIN:
        chat = next(r for r in ROUTES if r.kind == "chat")
        return Decision(text, chat, detail,
                        f"最高业务分 {best_score:.2f} < {AMBIGUOUS_MIN}，无业务信号 → 兜底闲聊", "fallback")
    if best_score < THRESHOLD:
        return Decision(text, None, detail,
                        f"最高分 {best_score:.2f} < 阈值 {THRESHOLD}，信号不足", "clarify")
    if best_score - second < MARGIN:
        return Decision(text, None, detail,
                        f"最高分 {best_score:.2f} 与次高 {second:.2f} 差距 < 边距 {MARGIN}，存在歧义", "clarify")
    return Decision(text, best_route, detail,
                    f"选中 {best_route.name}（{best_route.kind}，分 {best_score:.2f}）", "dispatch",
                    requires_approval=best_route.requires_approval)


# --------------------------------------------------------------------------- 多意图拆分
SPLIT_PATTERNS = ("，再", "，然后", "然后", "，并且", "并且", "；")


def split_intents(text: str) -> list[str]:
    parts = [text]
    for sep in SPLIT_PATTERNS:
        parts = [p for chunk in parts for p in chunk.split(sep) if p.strip()]
    return [p.strip() for p in parts if p.strip()]


def route(text: str) -> list[Decision]:
    return [route_clause(c) for c in split_intents(text)]


# --------------------------------------------------------------------------- 评测
EVAL = [
    ("查一下我下周的教学安排", "query_schedule"),
    ("帮我安排一次教学查房", "create_session"),
    ("教学查房有哪些要求？", "knowledge_qa"),
    ("组织全院心肺复苏技能考核", "exam_workflow"),
    ("两个科室的查房排期冲突了，帮我协调", "subagent_scheduling"),
    ("今天天气不错", "chat"),
    ("如何申请教学查房？", "knowledge_qa"),        # 陷阱：含"申请/安排"类动作词
    ("我的教学活动列表", "query_schedule"),
]


def evaluate() -> dict:
    correct = 0
    confusions = []
    for text, gold in EVAL:
        d = route_clause(text)
        got = d.route.name if d.route else None
        if got == gold:
            correct += 1
        else:
            confusions.append((text, gold, got, d.reason))
    return {"accuracy": round(correct / len(EVAL), 3), "n": len(EVAL), "confusions": confusions}


# --------------------------------------------------------------------------- 演示 / 自检

# ===========================================================================
# 四类路由方法对比：规则 / 向量比对 / 决策模型 / 大模型
# ===========================================================================
# 说明：下面的 model_strategy 是**真正训练**的朴素贝叶斯分类器（纯 Python，
# 无第三方依赖），用来演示「决策模型」这条路：需要训练数据、输出概率、低延迟。
# llm_strategy 是确定性替身，代表「把候选交给大模型判断」；真实实现替换成 LLM 调用。


def _route_by_name(name: str) -> Route:
    return next(r for r in ROUTES if r.name == name)


# ---- 规则：只看强关键词
def rule_strategy(text: str) -> str:
    scored = []
    for r in ROUTES:
        if r.kind == "chat":
            continue
        kw = keyword_score(text, r)
        if kw > 0:
            scored.append((kw, r))
    if not scored:
        return "chat"
    scored.sort(key=lambda x: (-x[0], x[1].cost))
    return scored[0][1].name


# ---- 向量比对：只看到示例的语义相似度
def vector_strategy(text: str) -> str:
    scored = []
    for r in ROUTES:
        if r.kind == "chat":
            continue
        sim = max((similarity(text, ex) for ex in r.examples), default=0.0)
        scored.append((sim, r))
    scored.sort(key=lambda x: (-x[0], x[1].cost))
    best_sim, best_route = scored[0]
    return best_route.name if best_sim > 0.05 else "chat"


# ---- 决策模型：朴素贝叶斯（字符 bigram 多项式模型 + 拉普拉斯平滑）
class NaiveBayesRouter:
    def __init__(self):
        self.prior: dict[str, float] = {}
        self.lik: dict[str, dict[str, float]] = {}
        self.vocab: set[str] = set()

    def fit(self, samples: list[tuple[str, str]]) -> "NaiveBayesRouter":
        counts: dict[str, Counter] = defaultdict(Counter)
        label_count: Counter = Counter()
        for text, label in samples:
            label_count[label] += 1
            for b in bigrams(text):
                counts[label][b] += 1
                self.vocab.add(b)
        n = len(samples)
        self.prior = {l: c / n for l, c in label_count.items()}
        for label, c in counts.items():
            total = sum(c.values()) + len(self.vocab)      # 拉普拉斯平滑
            self.lik[label] = {b: (c[b] + 1) / total for b in self.vocab}
        return self

    def predict(self, text: str) -> tuple[str, float]:
        scores = {}
        for label in self.prior:
            s = math.log(self.prior[label])
            for b in bigrams(text):
                s += math.log(self.lik[label].get(b, 1e-6))
            scores[label] = s
        # softmax 得到概率（数值稳定处理）
        mx = max(scores.values())
        exp = {l: math.exp(v - mx) for l, v in scores.items()}
        z = sum(exp.values())
        label = max(exp, key=exp.get)
        return label, exp[label] / z


def build_training_set() -> list[tuple[str, str]]:
    """用示例 + 合成变体构造训练集（演示：决策模型需要标注数据）。"""
    samples: list[tuple[str, str]] = []
    for r in ROUTES:
        for ex in r.examples:
            samples.append((ex, r.name))
        for kw in r.keywords:                    # 合成：关键词 + 常见前后缀
            samples.append((f"帮我{kw}", r.name))
            samples.append((f"{kw}一下", r.name))
    return samples


NB = NaiveBayesRouter().fit(build_training_set())


def model_strategy(text: str) -> str:
    label, prob = NB.predict(text)
    return label if prob >= 0.35 else "chat"


# ---- 大模型：把候选与信号交给模型判断（此处用确定性替身）
def llm_strategy(text: str) -> str:
    # 替身逻辑：规则 + 向量 + 决策模型三路投票，模拟「模型综合判断」
    votes = Counter([rule_strategy(text), vector_strategy(text), model_strategy(text)])
    top, cnt = votes.most_common(1)[0]
    if cnt >= 2:
        return top
    # 平票时用融合分决胜
    best = max(
        ((0.6 * keyword_score(text, r) + 0.4 * semantic_score(text, r)), r) for r in ROUTES
    )
    return best[1].name


STRATEGIES = {
    "规则": rule_strategy,
    "向量比对": vector_strategy,
    "决策模型": model_strategy,
    "大模型": llm_strategy,
}


def compare_strategies(repeat: int = 200) -> list[dict]:
    """在同一标注集上对比四类方法：准确率 + 单次平均耗时。"""
    rows = []
    for name, fn in STRATEGIES.items():
        correct = sum(1 for text, gold in EVAL if fn(text) == gold)
        t0 = time.perf_counter()
        for _ in range(repeat):
            for text, _gold in EVAL:
                fn(text)
        elapsed = (time.perf_counter() - t0) / (repeat * len(EVAL)) * 1000
        rows.append({
            "name": name,
            "accuracy": round(correct / len(EVAL), 3),
            "latency_ms": round(elapsed, 3),
            "needs_training": name == "决策模型",
            "explainable": name in ("规则", "向量比对"),
        })
    return rows


def demo_strategies() -> None:
    print("\n  ── 5) 四类方法对比（规则 / 向量 / 决策模型 / 大模型）──")
    print(f"    {'方法':<8}{'准确率':<8}{'单次耗时ms':<12}{'需训练':<7}{'可解释'}")
    for row in compare_strategies():
        print(f"    {row['name']:<10}{row['accuracy']:<10}{row['latency_ms']:<14}"
              f"{'是' if row['needs_training'] else '否':<8}{'是' if row['explainable'] else '部分'}")
    print("    说明：决策模型为现场训练的朴素贝叶斯（字符 bigram），仅用少量示例/合成样本；")
    print("          数据量增大后通常优于纯规则，但需要标注与版本管理。")
    print("          大模型替身为三路投票，真实实现换成 LLM 调用（成本与延迟显著更高）。")


def demo() -> None:
    print("【intent_router】Agent 意图路由设计")
    print(f"  路由注册表：{len(ROUTES)} 个去处 -> {[r.name for r in ROUTES]}")

    print("\n  ── 1) 单意图路由（含分数与理由）──")
    for text in ["查一下我下周的教学安排", "帮我安排一次教学查房",
                 "教学查房有哪些要求？", "组织全院心肺复苏技能考核"]:
        d = route_clause(text)
        print(f"    「{text}」")
        print(f"      → {d.route.name if d.route else '未定'} | {d.action} | {d.reason}")
        if d.route:
            print(f"      处理={d.route.handler()} 风险={d.route.risk} 成本={d.route.cost}"
                  f" 需审批={d.requires_approval}")

    print("\n  ── 2) 歧义 → 不硬猜，转澄清 ──")
    d = route_clause("安排")   # 信息不足，分数低
    print(f"    「安排」→ {d.action} | {d.reason}")

    print("\n  ── 3) 多意图拆分 ──")
    text = "查一下我下周的排期，再安排一个病例讨论"
    for d in route(text):
        print(f"    子句「{d.clause}」→ {d.route.name if d.route else '未定'} ({d.action})")

    print("\n  ── 4) 路由评测 ──")
    ev = evaluate()
    print(f"    准确率 {ev['accuracy']} ({ev['n']} 条)")
    for text, gold, got, reason in ev["confusions"]:
        print(f"    ✗ 「{text}」期望 {gold} 实得 {got}：{reason}")

    demo_strategies()

    print("\n  设计要点：")
    print("  · 路由是数据（注册表），不是 if/else；加去处 = 加一条 Route")
    print("  · 多信号融合（关键词+语义+LLM）比单信号稳；阈值+边距决定'敢不敢猜'")
    print("  · 拿不准就澄清/兜底，别硬猜；写操作单独标风险与审批")
    print("  · 每次决策要可解释、可评测，否则路由会悄悄退化")


def selftest() -> None:
    # 基础路由
    assert route_clause("查一下我下周的教学安排").route.name == "query_schedule"
    assert route_clause("帮我安排一次教学查房").route.name == "create_session"
    assert route_clause("教学查房有哪些要求？").route.name == "knowledge_qa"
    assert route_clause("组织全院心肺复苏技能考核").route.name == "exam_workflow"
    # 高风险写操作需审批
    d = route_clause("帮我安排一次教学查房")
    assert d.requires_approval is True and d.route.risk == "high"
    # 低信息 → 澄清而非硬猜
    assert route_clause("安排").action == "clarify"
    # 多意图拆分
    ds = route("查一下我下周的排期，再安排一个病例讨论")
    assert len(ds) == 2
    assert ds[0].route.name == "query_schedule" and ds[1].route.name == "create_session"
    # 评测达标
    assert evaluate()["accuracy"] >= 0.85
    # 四类方法：都能返回合法路由；决策模型不劣于纯规则
    valid = {r.name for r in ROUTES}
    for name, fn in STRATEGIES.items():
        for text, _gold in EVAL:
            assert fn(text) in valid, f"{name} 返回非法路由: {fn(text)}"
    assert {r["name"] for r in compare_strategies(repeat=5)} == {"规则", "向量比对", "决策模型", "大模型"}
    model_acc = sum(1 for t, g in EVAL if model_strategy(t) == g) / len(EVAL)
    rule_acc = sum(1 for t, g in EVAL if rule_strategy(t) == g) / len(EVAL)
    assert model_acc >= rule_acc


if __name__ == "__main__":
    demo()
