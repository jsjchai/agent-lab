#!/usr/bin/env python3
"""LangGraph 示例：临床教学案例生成器（带专家评审回环）。

这个例子想说明 LangGraph 的核心价值：**把 Agent 的流程画成一张图**，
于是"什么时候回退、最多回退几次、什么条件下结束"都是显式的、可测试的代码，
而不是藏在 prompt 里的一句"请你反复检查直到满意"。

流程：

    plan ──▶ draft_case ──▶ design_questions ──▶ review ──┬──(score < 80 且 修订 < 2 次)──▶ revise ──┐
                                                           │                                        │
                                                           │◀───────────────────────────────────────┘
                                                           └──(通过 / 修订次数用尽)──▶ finalize ──▶ END

运行（离线，无需 API key）：

    cd code/07-frameworks/medical-education
    ../../../.venv/bin/python langgraph_case_agent.py

换真实模型：

    AGENT_LLM=openai OPENAI_API_KEY=sk-... AGENT_MODEL=gpt-4o-mini \
      ../../../.venv/bin/python langgraph_case_agent.py --topic "急性胸痛"

想看图的定义：

    ../../../.venv/bin/python langgraph_case_agent.py --show-graph
"""

from __future__ import annotations

import argparse
import operator
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.graph import END, START, StateGraph  # noqa: E402

from common.llm import LLMClient, describe, extract_json  # noqa: E402

PASS_SCORE = 80
MAX_REVISIONS = 2


# --------------------------------------------------------------------------- 状态
class TeachingState(TypedDict, total=False):
    """整张图共享的状态。

    LangGraph 的做法：每个节点只返回它改动的字段，框架负责合并。
    `notes` / `reviews` 用 operator.add 变成"追加"，而不是覆盖。
    """

    topic: str          # 教学主题
    level: str          # 学习者层级
    objectives: str     # 教学目标
    case_text: str      # 教学病例
    questions: str      # 分层问题
    review: dict        # 最近一次评审结果
    revisions: int      # 已修订次数
    reviews: Annotated[list[dict], operator.add]
    notes: Annotated[list[str], operator.add]
    final_markdown: str  # finalize 节点的产出


# --------------------------------------------------------------------------- 构图
def build_graph(llm: LLMClient):
    """把流程搭成图。节点内部只做"调用模型 + 返回状态增量"。"""

    def plan(state: TeachingState) -> dict:
        print("  ▶ plan            设计教学目标")
        system = "你是三甲医院内科的教学设计师，熟悉 Bloom 分类与住培教学大纲。只输出教学目标与安排，不要寒暄。"
        user = (
            f"教学主题：{state['topic']}\n"
            f"学习者：{state['level']}\n"
            "请设计 3 条可观察、可评价的教学目标（知识/技能/素养各一条），"
            "并给出时长分配与评价方式建议。"
        )
        return {"objectives": llm.complete("plan", system, user), "notes": ["plan 完成"]}

    def draft_case(state: TeachingState) -> dict:
        print("  ▶ draft_case      生成教学病例")
        system = (
            "你是临床教学病例编写者。要求：病例为模拟病例，资料足以训练初始评估，"
            "但故意保留信息缺口，迫使学习者主动提问。不要给出诊断结论。"
        )
        user = (
            f"教学主题：{state['topic']}\n"
            f"已定教学目标：\n{state['objectives']}\n"
            "请写一份教学病例，包含主诉、现病史、既往史、查体、辅助检查，"
            "并在末尾写一段「教学提示」说明设计意图。"
        )
        return {"case_text": llm.complete("case", system, user), "notes": ["draft_case 完成"]}

    def design_questions(state: TeachingState) -> dict:
        print("  ▶ design_questions 设计分层问题")
        system = "你是临床带教老师，擅长用问题驱动学习。问题必须分层，并给出参考答案与评分要点。"
        user = (
            f"教学主题：{state['topic']}\n"
            f"病例：\n{state['case_text']}\n"
            "请出 3 道题，分别对应记忆/理解、应用、分析/评价三个层次，"
            "每题给出参考答案和评分要点。"
        )
        return {"questions": llm.complete("questions", system, user), "notes": ["design_questions 完成"]}

    def review(state: TeachingState) -> dict:
        print("  ▶ review           专家评审（打分 + 问题清单）")
        system = (
            "你是严格的教学督导。按「目标—病例—问题」一致性打分（0-100），"
            "并列出必须修改的具体问题。只输出 JSON："
            '{"score": int, "verdict": "pass"|"needs_revision", "issues": [str], "suggestion": str}'
        )
        user = (
            f"教学主题：{state['topic']}\n学习者：{state['level']}\n"
            f"教学目标：\n{state['objectives']}\n\n"
            f"教学病例：\n{state['case_text']}\n\n"
            f"分层问题：\n{state['questions']}\n\n"
            "请评审。注意：病例是否支持目标？问题是否真正分层？有没有临床错误？"
        )
        result = extract_json(llm.complete("review", system, user, temperature=0.1))
        print(f"    评分 {result.get('score')}（{result.get('verdict')}），问题 {len(result.get('issues', []))} 条")
        return {"review": result, "reviews": [result], "notes": [f"review 评分 {result.get('score')}"]}

    def revise(state: TeachingState) -> dict:
        n = state.get("revisions", 0) + 1
        print(f"  ▶ revise           第 {n} 次修订（针对评审意见）")
        system = "你是教学病例修订者。逐条回应评审意见，保留原有可用内容，输出修订后的完整版本。"
        issues = state.get("review", {}).get("issues", [])
        user = (
            f"教学主题：{state['topic']}\n"
            f"原病例：\n{state['case_text']}\n\n"
            f"原问题：\n{state['questions']}\n\n"
            "评审意见：\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
            "请输出修订后的病例与问题（含修订说明）。"
        )
        return {
            "case_text": llm.complete("revise", system, user),
            "revisions": n,
            "notes": [f"revise 第 {n} 次"],
        }

    def finalize(state: TeachingState) -> dict:
        print("  ▶ finalize         组装教案 Markdown")
        reviews = state.get("reviews", [])
        score = state.get("review", {}).get("score", "-")
        rows = "\n".join(
            f"| 第 {i + 1} 轮 | {r.get('score')} | {r.get('verdict')} | "
            f"{'；'.join(r.get('issues', [])) or '无'} |"
            for i, r in enumerate(reviews)
        )
        markdown = f"""# {state['topic']} · 临床教学案例教案

> 由 LangGraph 示例自动生成于 {datetime.now():%Y-%m-%d %H:%M}
> 学习者：{state['level']} ｜ 评审得分：{score} ｜ 修订次数：{state.get('revisions', 0)}

## 一、教学目标

{state.get('objectives', '')}

## 二、教学病例

{state.get('case_text', '')}

## 三、分层问题与评分要点

{state.get('questions', '')}

## 四、评审记录

| 轮次 | 得分 | 结论 | 主要意见 |
|---|---|---|---|
{rows}

## 五、使用说明

- 本教案为**模拟病例**，不含真实患者信息；用于教学演练，不构成诊疗建议。
- 建议课前把病例打印成「信息卡」，按教学节奏逐条释放，制造"信息不全"的判断点。
- 课后用同一批问题复测，比较前后得分，作为形成性评价依据。
"""
        return {"final_markdown": markdown}

    # -- 条件边：这里就是"回环"的全部逻辑，显式、可测
    def route_after_review(state: TeachingState) -> str:
        review = state.get("review", {})
        score = review.get("score", 0)
        revisions = state.get("revisions", 0)
        if score >= PASS_SCORE or revisions >= MAX_REVISIONS:
            return "finalize"
        return "revise"

    graph = StateGraph(TeachingState)
    for name, fn in [
        ("plan", plan),
        ("draft_case", draft_case),
        ("design_questions", design_questions),
        ("review", review),
        ("revise", revise),
        ("finalize", finalize),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "draft_case")
    graph.add_edge("draft_case", "design_questions")
    graph.add_edge("design_questions", "review")
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"revise": "revise", "finalize": "finalize"},
    )
    graph.add_edge("revise", "review")   # 回环
    graph.add_edge("finalize", END)

    return graph.compile()


# --------------------------------------------------------------------------- CLI
def main() -> int:
    parser = argparse.ArgumentParser(description="LangGraph 医疗教学案例生成示例")
    parser.add_argument("--topic", default="社区获得性肺炎（CAP）", help="教学主题")
    parser.add_argument("--level", default="住院医师规范化培训第一年（R1）", help="学习者层级")
    parser.add_argument("--out", default="out/langgraph_teaching_case.md", help="输出 Markdown 路径")
    parser.add_argument("--show-graph", action="store_true", help="打印 Mermaid 图定义后退出")
    args = parser.parse_args()

    print(f"【LangGraph 示例】{describe()}")

    llm = LLMClient()
    app = build_graph(llm)

    if args.show_graph:
        print(app.get_graph().draw_mermaid())
        return 0

    initial: TeachingState = {
        "topic": args.topic,
        "level": args.level,
        "revisions": 0,
        "reviews": [],
        "notes": [],
    }

    print(f"\n开始生成：{args.topic} / {args.level}")
    # recursion_limit 是"防跑飞"的保险丝：节点执行步数上限
    state = app.invoke(initial, config={"recursion_limit": 30})

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(state["final_markdown"], encoding="utf-8")

    print("\n执行轨迹：")
    for note in state.get("notes", []):
        print(f"  · {note}")

    print(f"\n✅ 已生成：{out_path}")
    print(f"   评审轮次：{len(state.get('reviews', []))} ｜ 修订：{state.get('revisions', 0)} 次")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportError as exc:  # 友好提示，而不是抛一堆栈
        print(f"缺少依赖：{exc}\n请先运行：uv pip install --python .venv/bin/python langgraph", file=sys.stderr)
        raise SystemExit(1) from exc
