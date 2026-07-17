#!/usr/bin/env python3
"""mes1 Web Agent —— FastAPI 服务（SSE 流式对话）。

把 core.engine.agent_loop 包成 HTTP 接口：
  POST /api/chat        -> SSE 流（session / assistant_text / tool_use /
                           tool_result / error / done）
  GET  /api/sessions     -> 会话列表
  DELETE /api/sessions/{id} -> 删除会话
  GET  /api/health       -> 健康检查
  GET  /api/info         -> 模型 + 工具清单

运行（必须在项目根目录，确保 config/core/tools/services 可导入）：
  cd D:/Agent/0-1claude
  venv/Scripts/python.exe -m uvicorn api.server:app --host 0.0.0.0 --port 5000
"""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

# 把项目根目录与 api/ 都加入 sys.path，保证两类 import 都能解析：
#   from config import * / from core.engine import *  （项目根）
#   import session_store                                （api/ 目录）
_ROOT = Path(__file__).resolve().parent.parent
_API = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

# ── 启动时初始化工具 handler（与 app.py 一致）──
from tools.builtin import init_builtin_handlers, init_sub_handlers, BUILTIN_HANDLERS
init_builtin_handlers()
init_sub_handlers()

from core.engine import agent_loop
from services.cron import agent_lock
from config import PRIMARY_MODEL
import session_store as store

app = FastAPI(title="mes1 Web Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/api/health")
def health():
    return {"status": "ok", "model": PRIMARY_MODEL}


@app.get("/api/info")
def info():
    return {
        "model": PRIMARY_MODEL,
        "tool_count": len(BUILTIN_HANDLERS),
        "tools": sorted(BUILTIN_HANDLERS.keys()),
    }


@app.get("/api/sessions")
def sessions():
    return [
        {
            "id": s.id,
            "title": s.title,
            "message_count": len(s.messages),
            "updated_at": s.updated_at,
        }
        for s in store.list_sessions()
    ]


@app.delete("/api/sessions/{sid}")
def del_session(sid: str):
    ok = store.delete_session(sid)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    s = store.get_session(req.session_id)
    if s is None:
        s = store.create_session()
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="empty message")

    s.messages.append({"role": "user", "content": req.message})
    if s.title == "新会话":
        s.title = req.message[:30]
    s.updated_at = time.time()

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    # sink 在 worker 线程调用，必须用 call_soon_threadsafe 跨线程投递到事件循环
    def sink(event: dict):
        loop.call_soon_threadsafe(q.put_nowait, event)

    def run():
        try:
            # agent_lock 串行保护：与 CLI 行为一致，避免并发跑 agent_loop
            with agent_lock:
                res = agent_loop(s.messages, s.context, sink=sink)
            s.context = res
            loop.call_soon_threadsafe(q.put_nowait, {"type": "done"})
        except Exception as e:  # 兜底：任何异常都转为 error + done
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "error", "message": f"{type(e).__name__}: {str(e)[:500]}"},
            )
            loop.call_soon_threadsafe(q.put_nowait, {"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    async def event_stream():
        yield _sse({"type": "session", "session_id": s.id})
        while True:
            event = await q.get()
            yield _sse(event)
            if event.get("type") == "done":
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
