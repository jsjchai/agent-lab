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


if __name__ == "__main__":
    demo()
