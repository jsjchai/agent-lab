#!/usr/bin/env python3
"""m05 · Agent 工作流编排：State / Graph / Checkpoint / HITL —— 对应文档 §6。

用 LangGraph 实现文档 §6 的「Teaching 首期活动创建流程」：

    用户输入 -> 意图/字段抽取 -> 缺项判断
        有缺项 -> 向用户澄清并等待补充（interrupt）
        无缺项 -> 调用只读业务工具 -> 生成草稿 -> 业务规则校验
              -> 展示草稿 + 用户确认（interrupt + 一次性凭证）
              -> 调用 Teaching 既有业务 API 创建 -> 返回结果

关键工程点（文档 §6 设计原则）：
- 单 Agent + 显式工作流，不急于 Multi-Agent。
- 状态持久化到 SQLite（SqliteSaver），服务重启后可恢复（Checkpoint）。
- 人工确认绑定 用户/租户/草稿哈希/有效期/一次性凭证（HITL）。
- 最终写操作由原业务服务执行（common.business.create_activity_api）。
- 最大澄清轮数 + recursion_limit，防止无限循环。

运行（离线，演示完整流程，含模拟重启）：
    ../../.venv/bin/python m05_workflow.py
CLI（真实分步，跨进程恢复）：
    ../../.venv/bin/python m05_workflow.py start --user u1 --text "帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人"
    ../../.venv/bin/python m05_workflow.py resume --task-id <ID> --user u1 --input "11月20日，主讲人：张三、李四"
    ../../.venv/bin/python m05_workflow.py resume --task-id <ID> --user u1 --confirm-token <TOKEN>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import m02_intent_slots as m02
import m04_tools as m04
from common import business
from common.llm import LLM
from common.security import AuditLog, AuthError, ConfirmTokenStore, PersistentConfirmTokenStore, SecurityContext, authenticate

MAX_CLARIFY_ROUNDS = 3
DEFAULT_DB = str(Path(__file__).resolve().parent / "out" / "workflow.db")


class FlowState(TypedDict, total=False):
    task_id: str
    user_text: str
    slots: dict
    missing: list
    questions: list
    draft: dict
    errors: list
    clarify_rounds: int
    status: str
    activity_id: str
    confirm_token: str


def build_graph(ctx: SecurityContext, llm: LLM, reg: m04.ToolRegistry,
                tokens: ConfirmTokenStore, checkpointer):
    """ctx 通过闭包注入（每次调用都来自可信认证链路），不存进 checkpoint。"""

    def extract(state: FlowState) -> dict:
        result = m02.recognize(llm, state["user_text"])
        slots = {**state.get("slots", {}), **result.get("slots", {})}
        return {
            "slots": slots,
            "missing": result.get("missingFields", []),
            "questions": result.get("questions", []),
        }

    def route_extract(state: FlowState) -> str:
        if not state.get("missing"):
            return "gather"
        if state.get("clarify_rounds", 0) >= MAX_CLARIFY_ROUNDS:
            return "fail"
        return "clarify"

    def clarify(state: FlowState) -> dict:
        answer = interrupt({"type": "clarification", "questions": state["questions"]})
        return {
            "user_text": state["user_text"] + "。补充：" + str(answer),
            "clarify_rounds": state.get("clarify_rounds", 0) + 1,
        }

    def gather(state: FlowState) -> dict:
        task = state["task_id"]
        reg.call("query_activity_rules", ctx, {}, task)
        scope = reg.call("query_org_scope", ctx, {}, task)
        # 在授权范围内确认主讲人存在
        for org in scope["org_ids"]:
            reg.call("search_participants", ctx, {"org_id": org}, task)
        return {"status": "gathered"}

    def draft(state: FlowState) -> dict:
        d = reg.call("build_activity_draft", ctx, {"slots": state["slots"]}, state["task_id"])
        return {"draft": d}

    def validate(state: FlowState) -> dict:
        result = reg.call("validate_activity_draft", ctx, {"draft": state["draft"]}, state["task_id"])
        return {"errors": result["errors"]}

    def route_validate(state: FlowState) -> str:
        if not state.get("errors"):
            return "confirm"
        if state.get("clarify_rounds", 0) >= MAX_CLARIFY_ROUNDS:
            return "fail"
        return "fix"

    def fix(state: FlowState) -> dict:
        answer = interrupt({"type": "validation_error", "errors": state["errors"]})
        return {
            "user_text": state["user_text"] + "。修正：" + str(answer),
            "clarify_rounds": state.get("clarify_rounds", 0) + 1,
        }

    def confirm(state: FlowState) -> dict:
        token = tokens.issue(ctx, state["draft"])
        payload = interrupt({"type": "confirmation", "draft": state["draft"], "token": token})
        # 用户回传凭证；consume 校验 用户/租户/哈希/有效期/一次性
        tokens.consume(str(payload), ctx, state["draft"])
        return {"confirm_token": str(payload), "status": "confirmed"}

    def create(state: FlowState) -> dict:
        result = business.create_activity_api(ctx, state["draft"], idempotency_key=state["task_id"])
        return {"activity_id": result["activity_id"], "status": "done"}

    def fail(state: FlowState) -> dict:
        return {"status": "failed"}

    g = StateGraph(FlowState)
    for name, fn in [("extract", extract), ("clarify", clarify), ("gather", gather),
                     ("draft", draft), ("validate", validate), ("fix", fix),
                     ("confirm", confirm), ("create", create), ("fail", fail)]:
        g.add_node(name, fn)

    g.add_edge(START, "extract")
    g.add_conditional_edges("extract", route_extract, {"gather": "gather", "clarify": "clarify", "fail": "fail"})
    g.add_edge("clarify", "extract")
    g.add_edge("gather", "draft")
    g.add_edge("draft", "validate")
    g.add_conditional_edges("validate", route_validate, {"confirm": "confirm", "fix": "fix", "fail": "fail"})
    g.add_edge("fix", "extract")
    g.add_edge("confirm", "create")
    g.add_edge("create", END)
    g.add_edge("fail", END)
    return g.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------- 运行辅助
def _open(db: str):
    conn = sqlite3.connect(db, check_same_thread=False)
    return conn, SqliteSaver(conn)


def _interrupt_payload(graph, config):
    state = graph.get_state(config)
    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def start_task(user: str, text: str, db: str = DEFAULT_DB) -> dict:
    ctx = authenticate(user)
    conn, saver = _open(db)
    reg = m04.build_registry(AuditLog())
    graph = build_graph(ctx, LLM(), reg, ConfirmTokenStore(), saver)
    task_id = "task-" + uuid.uuid4().hex[:8]
    config = {"configurable": {"thread_id": task_id}}
    graph.invoke({"task_id": task_id, "user_text": text, "clarify_rounds": 0}, config)
    payload = _interrupt_payload(graph, config)
    conn.close()
    return {"task_id": task_id, "interrupt": payload}


def resume_task(task_id: str, user: str, value: str, db: str = DEFAULT_DB,
                tokens: ConfirmTokenStore | None = None) -> dict:
    # 重新认证 + 重建 graph/saver，模拟服务重启后恢复
    ctx = authenticate(user)
    conn, saver = _open(db)
    reg = m04.build_registry(AuditLog())
    graph = build_graph(ctx, LLM(), reg, tokens or ConfirmTokenStore(), saver)
    config = {"configurable": {"thread_id": task_id}}
    # 已结束的任务没有待处理中断，拒绝继续（防止对已完成任务重放凭证）
    pre = graph.get_state(config)
    if not pre.tasks or not any(t.interrupts for t in pre.tasks):
        conn.close()
        raise AuthError("任务已结束或不存在待处理中断，无法继续")
    graph.invoke(Command(resume=value), config)
    state = graph.get_state(config)
    payload = _interrupt_payload(graph, config)
    conn.close()
    return {"task_id": task_id, "interrupt": payload, "values": state.values}


# --------------------------------------------------------------------------- 演示 / 自检
def demo() -> None:
    print("【m05 工作流】State + Graph + Checkpoint + HITL")
    db = str(Path(__file__).resolve().parent / "out" / "demo_workflow.db")
    Path(db).unlink(missing_ok=True)
    business.reset_for_test()

    # 共享凭证存储（跨"重启"保持，模拟 Redis/DB）
    tokens = ConfirmTokenStore()

    print("\n  1) start：输入缺项需求")
    r = start_task("u1", "帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人", db)
    task_id = r["task_id"]
    print("     中断类型:", r["interrupt"]["type"], "问题:", r["interrupt"]["questions"])

    print("\n  2) resume（模拟重启）：补充日期与主讲人")
    r = resume_task(task_id, "u1", "11月20日，主讲人：张三、李四", db, tokens)
    print("     中断类型:", r["interrupt"]["type"])
    draft = r["interrupt"]["draft"]
    token = r["interrupt"]["token"]
    print("     草稿:", draft["title"], "| 凭证:", token[:12] + "…")

    print("\n  3) resume（再次重启）：用户确认")
    r = resume_task(task_id, "u1", token, db, tokens)
    print("     最终状态:", r["values"].get("status"), "| activity_id:", r["values"].get("activity_id"))
    print("     业务表活动数:", business.activity_count())

    print("\n  4) 重放凭证应被拒绝：")
    try:
        resume_task(task_id, "u1", token, db, tokens)
        print("     ✗ 重放未被拒绝")
    except AuthError as exc:
        print("     ✓ 重放被拒绝 ->", exc)


def selftest() -> None:
    db = str(Path(__file__).resolve().parent / "out" / "test_workflow.db")
    Path(db).unlink(missing_ok=True)
    business.reset_for_test()
    tokens = ConfirmTokenStore()

    r = start_task("u1", "帮我创建下周的数学教研活动，面向三年级教师，安排两位主讲人", db)
    assert r["interrupt"]["type"] == "clarification"
    task_id = r["task_id"]

    r = resume_task(task_id, "u1", "11月20日，主讲人：张三、李四", db, tokens)
    assert r["interrupt"]["type"] == "confirmation"
    token = r["interrupt"]["token"]
    draft = r["interrupt"]["draft"]

    r = resume_task(task_id, "u1", token, db, tokens)
    assert r["values"]["status"] == "done"
    assert business.activity_count() == 1

    # 重放拒绝
    try:
        resume_task(task_id, "u1", token, db, tokens)
        raise AssertionError("重放应被拒绝")
    except AuthError:
        pass
    assert business.activity_count() == 1  # 没有重复创建


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("start"); p.add_argument("--user", required=True); p.add_argument("--text", required=True); p.add_argument("--db", default=DEFAULT_DB)
    p = sub.add_parser("resume"); p.add_argument("--task-id", required=True); p.add_argument("--user", required=True); p.add_argument("--input"); p.add_argument("--confirm-token"); p.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()

    if args.cmd == "start":
        print(json.dumps(start_task(args.user, args.text, args.db), ensure_ascii=False, indent=2))
    elif args.cmd == "resume":
        value = args.confirm_token or args.input
        token_db = str(Path(args.db).parent / "tokens.db")
        store = PersistentConfirmTokenStore(token_db)
        print(json.dumps(resume_task(args.task_id, args.user, value, args.db, store), ensure_ascii=False, indent=2))
    else:
        demo()
