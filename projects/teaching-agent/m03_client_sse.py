#!/usr/bin/env python3
"""m03 · 模型接入与流式接口 —— 对应文档 §5（Spring AI 的 Python 替代）。

Spring AI 能力 → Python 对应：
    ChatClient / ChatModel   -> common.llm.LLM.chat()
    Structured Output        -> LLM.chat_json() + pydantic（见 m01）
    Streaming / SSE          -> LLM.stream() + FastAPI StreamingResponse（本例）
    Retry / Timeout          -> OpenAI client timeout/max_retries（见 common/llm.py）
    Token 统计               -> LLM.stats

本例提供一个最小 FastAPI 服务，含普通对话与 SSE 流式两个接口，
并演示「不向前端返回原始内部异常」「流式断连/超时处理」的工程要求。

运行演示（离线，不起服务）：
    ../../.venv/bin/python m03_client_sse.py
启动真实服务：
    ../../.venv/bin/python m03_client_sse.py --serve     # http://127.0.0.1:7870
    curl -N "http://127.0.0.1:7870/chat/stream?text=你好"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from common.llm import LLM, describe


def build_app(llm: LLM | None = None) -> FastAPI:
    llm = llm or LLM()
    app = FastAPI(title="Teaching AI 模型接入示例")

    @app.post("/chat")
    def chat(body: dict):
        text = body.get("text", "")
        try:
            reply = llm.chat([{"role": "user", "content": text}])
            return {"reply": reply, "stats": llm.stats}
        except Exception:
            # 工程要求：不向前端返回原始内部异常
            return JSONResponse({"error": "模型服务暂时不可用，请稍后重试"}, status_code=503)

    @app.get("/chat/stream")
    def chat_stream(text: str = "你好"):
        def gen():
            try:
                for chunk in llm.stream([{"role": "user", "content": text}]):
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception:
                yield f"data: {json.dumps({'error': 'stream interrupted'})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def demo() -> None:
    print(f"【m03 模型接入/SSE】{describe()}")
    llm = LLM()

    print("\n  普通对话：")
    print("   ", llm.chat([{"role": "user", "content": "你好"}]))

    print("\n  流式输出（模拟 SSE chunk）：")
    chunks = list(llm.stream([{"role": "user", "content": "介绍一下教研活动"}]))
    print("    收到", len(chunks), "个 chunk，拼接长度", sum(len(c) for c in chunks))

    print(f"\n  Token 统计：{llm.stats}")
    print("\n  启动服务：python m03_client_sse.py --serve")


def selftest() -> None:
    from fastapi.testclient import TestClient

    app = build_app(LLM("mock"))
    client = TestClient(app)

    r = client.post("/chat", json={"text": "你好"})
    assert r.status_code == 200 and "reply" in r.json()

    with client.stream("GET", "/chat/stream", params={"text": "你好"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in resp.iter_lines() if ln.startswith("data:")]
    assert lines and lines[-1] == "data: [DONE]"
    assert any("[DONE]" not in ln for ln in lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=7870)
    args = parser.parse_args()
    if args.serve:
        import uvicorn

        uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")
    else:
        demo()
