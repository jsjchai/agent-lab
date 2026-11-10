#!/usr/bin/env python3
"""两个 Agent 示例的可视化后端：把运行过程以 SSE 流式推给网页。

用法：
    cd code/07-frameworks/medical-education
    ../../../.venv/bin/python webui/server.py
    # 打开 http://127.0.0.1:7861

设计要点：
- 不 import 两个示例脚本，而是**起子进程**跑它们（带 --emit-json）。
  子进程可以超时杀掉，CrewAI 的 import 副作用也不会污染 Web 进程。
- stderr 重定向到临时文件而不是管道：事件模式下人类日志全走 stderr，
  用管道会被写满导致死锁（这是这类桥接最常见的坑）。
- 读 stdout 用线程 + 队列，主循环带超时，保证"卡住的模型"不会挂死服务。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
BASE = HERE.parent                 # medical-education/
STATIC = HERE / "static"
PY = sys.executable

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODELS = ["mock", "qwen2.5:7b", "qwen3:8b"]
RUN_TIMEOUT = float(os.getenv("WEB_RUN_TIMEOUT", "600"))  # 单次运行上限（秒）

app = FastAPI(title="医疗教学 Agent 可视化", docs_url=None, redoc_url=None)


@app.get("/")
def index():
    page = STATIC / "index.html"
    if not page.exists():
        return JSONResponse({"error": "前端页面未就绪"}, status_code=503)
    return FileResponse(page)


@app.get("/api/health")
def health():
    return {"ok": True, "models": MODELS, "default": "mock", "base": BASE.name}


def _build(example: str, topic: str, model: str) -> tuple[list[str], dict, str]:
    """拼子进程命令与环境变量。返回 (cmd, env, out_md)。"""
    env = os.environ.copy()
    if example == "langgraph":
        out_md = "out/web_langgraph.md"
        cmd = [PY, "langgraph_case_agent.py", "--emit-json", "--topic", topic, "--out", out_md]
        if model != "mock":
            cmd += ["--model", model]
    elif example == "crewai":
        out_md = "out/web_crewai.md"
        cmd = [PY, "crewai_teaching_activity.py", "--emit-json", "--topic", topic, "--out", out_md]
    else:
        raise ValueError(f"未知示例：{example}")

    if model == "mock":
        env["AGENT_LLM"] = "mock"
    else:
        env.update(
            {
                "AGENT_LLM": "openai",
                "AGENT_MODEL": model,
                "OPENAI_BASE_URL": OLLAMA_BASE,
                "OPENAI_API_KEY": "ollama",
                "AGENT_TIMEOUT": "180",
            }
        )
    return cmd, env, out_md


def _pump(stream, q: queue.Queue) -> None:
    """子进程 stdout → 队列（阻塞读放在线程里，主循环才能做超时判断）。"""
    try:
        for line in stream:
            q.put(line)
    finally:
        q.put(None)


@app.get("/api/run")
def run(example: str = "langgraph", topic: str = "", model: str = "mock"):
    if example not in {"langgraph", "crewai"}:
        return JSONResponse({"error": f"未知示例：{example}"}, status_code=400)
    topic = (topic or "").strip() or "社区获得性肺炎（CAP）"
    if model not in MODELS:
        model = "mock"

    cmd, env, out_md = _build(example, topic, model)

    def stream():
        started = time.time()
        deadline = started + RUN_TIMEOUT
        q: queue.Queue = queue.Queue()
        errfile = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            cmd, cwd=BASE, env=env, stdout=subprocess.PIPE,
            stderr=errfile, text=True, bufsize=1,
        )
        threading.Thread(target=_pump, args=(proc.stdout, q), daemon=True).start()
        saw_done = False
        try:
            while True:
                try:
                    line = q.get(timeout=1.0)
                except queue.Empty:
                    if time.time() > deadline:
                        proc.kill()
                        yield _sse({"type": "error", "message": f"运行超过 {RUN_TIMEOUT:.0f} 秒已终止"})
                        return
                    continue
                if line is None:
                    break
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "done":
                    saw_done = True
                yield _sse(event)

            code = proc.wait(timeout=30)
            if not saw_done:
                errfile.seek(0)
                tail = errfile.read()[-1200:]
                yield _sse(
                    {
                        "type": "error",
                        "message": f"进程退出码 {code}，未收到完成事件",
                        "detail": tail,
                    }
                )
        finally:
            if proc.poll() is None:
                proc.kill()
            errfile.close()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# 静态资源必须**最后**挂载：Starlette 按注册顺序匹配，
# 挂在 "/" 会兜住所有未匹配路径（style.css / app.js 就靠它）。
# 放前面会把 /api/* 一起截胡。
app.mount("/", StaticFiles(directory=STATIC, html=True, check_dir=False), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "7861"))
    print(f"页面地址：http://127.0.0.1:{port}")
    print(f"工作目录：{BASE}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
