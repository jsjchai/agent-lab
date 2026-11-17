#!/usr/bin/env python3
"""Teaching Agent 可视化后端：交互式活动创建工作流 + 知识问答 + 评测/安全面板。

与医疗示例的 SSE 子进程模式不同，这里的工作流是**交互式**的（interrupt 暂停/恢复），
所以用请求/响应：前端 start → 收到澄清/确认中断 → 用户作答 → resume → 直到完成。
状态持久化在 SQLite，刷新页面后用 task_id 仍可恢复（对应文档 §6 Checkpoint）。

用法：
    cd projects/teaching-agent
    ../../.venv/bin/python webui/server.py
    # 打开 http://127.0.0.1:7871
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

import m04_tools as m04
import m05_workflow as m05
import m06_rag as m06
import m07_security as m07
import m08_eval as m08
from common.llm import LLM, describe
from common.security import (AuditLog, AuthError, PersistentConfirmTokenStore, authenticate)

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
STATIC = HERE / "static"
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)

# 持久化：checkpoint + 一次性凭证（跨请求/重启共享）
_conn = sqlite3.connect(str(OUT / "web_workflow.db"), check_same_thread=False)
_SAVER = SqliteSaver(_conn)
_TOKENS = PersistentConfirmTokenStore(str(OUT / "web_tokens.db"))
_USERS = ["u1", "u2", "u3"]

app = FastAPI(title="Teaching Agent 可视化", docs_url=None, redoc_url=None)


def _graph(ctx):
    reg = m04.build_registry(AuditLog())
    return m05.build_graph(ctx, LLM(), reg, _TOKENS, _SAVER)


def _snapshot(graph, config) -> dict:
    state = graph.get_state(config)
    vals = state.values
    interrupt = None
    for task in state.tasks:
        if task.interrupts:
            interrupt = task.interrupts[0].value
            break
    return {
        "trace": vals.get("trace", []),
        "interrupt": interrupt,
        "done": vals.get("status") in ("done", "failed"),
        "state": {
            "slots": vals.get("slots", {}),
            "missing": vals.get("missing", []),
            "questions": vals.get("questions", []),
            "draft": vals.get("draft", {}),
            "errors": vals.get("errors", []),
            "status": vals.get("status", ""),
            "activity_id": vals.get("activity_id", ""),
            "clarify_rounds": vals.get("clarify_rounds", 0),
        },
    }


@app.get("/")
def index():
    page = STATIC / "index.html"
    if not page.exists():
        return JSONResponse({"error": "前端页面未就绪"}, status_code=503)
    return FileResponse(page)


@app.get("/api/health")
def health():
    return {"ok": True, "users": _USERS, "llm": describe(), "base": BASE.name}


@app.post("/api/workflow/start")
def workflow_start(body: dict):
    user = body.get("user", "u1")
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "请输入活动需求"}, status_code=400)
    try:
        ctx = authenticate(user)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    graph = _graph(ctx)
    task_id = "task-" + uuid.uuid4().hex[:8]
    config = {"configurable": {"thread_id": task_id}}
    graph.invoke({"task_id": task_id, "user_text": text, "clarify_rounds": 0, "trace": []}, config)
    return {"task_id": task_id, **_snapshot(graph, config)}


@app.post("/api/workflow/resume")
def workflow_resume(body: dict):
    task_id = body.get("task_id", "")
    user = body.get("user", "u1")
    value = body.get("value", "")
    try:
        ctx = authenticate(user)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    graph = _graph(ctx)
    config = {"configurable": {"thread_id": task_id}}
    pre = graph.get_state(config)
    if not pre.tasks or not any(t.interrupts for t in pre.tasks):
        return JSONResponse({"error": "任务已结束或不存在待处理中断"}, status_code=409)
    try:
        graph.invoke(Command(resume=value), config)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    return {"task_id": task_id, **_snapshot(graph, config)}


@app.get("/api/workflow/status")
def workflow_status(task_id: str, user: str = "u1"):
    try:
        ctx = authenticate(user)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    graph = _graph(ctx)
    config = {"configurable": {"thread_id": task_id}}
    if not graph.get_state(config).values:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    return {"task_id": task_id, **_snapshot(graph, config)}


@app.post("/api/rag")
def rag(body: dict):
    user = body.get("user", "u1")
    query = (body.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "请输入问题"}, status_code=400)
    try:
        ctx = authenticate(user)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    index = m06.KnowledgeIndex(LLM())
    index.build()
    retrieved = index.retrieve(ctx, query, k=3)
    ans = index.answer(ctx, query)
    return {
        "answer": ans["answer"],
        "citations": ans["citations"],
        "chunks": [
            {"chunk_id": c["chunk_id"], "doc_title": c["doc_title"], "section": c["section"],
             "tenant": c["tenant"], "text": c["text"]}
            for c in retrieved
        ],
        "user_tenant": ctx.tenant_id,
    }


@app.get("/api/eval")
def eval_report():
    result = m08.run()
    return {"metrics": result["metrics"], "thresholds": m08.THRESHOLDS,
            "details": result["details"], "total": result["total"]}


@app.get("/api/security")
def security():
    return {"tests": [{"name": name, "passed": fn()} for name, fn in m07.TESTS]}


# 静态资源最后挂载，避免截胡 /api/*
app.mount("/", StaticFiles(directory=STATIC, html=True, check_dir=False), name="static")


if __name__ == "__main__":
    import uvicorn

    import os

    port = int(os.getenv("PORT", "7871"))
    print(f"页面地址：http://127.0.0.1:{port}")
    print(f"工作目录：{BASE}")
    print(describe())
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
