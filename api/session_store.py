"""会话状态存储（内存版）。

每个会话持有自己的 messages 列表与 context 字典，
直接喂给 core.engine.agent_loop(messages, context) —— 与 CLI 的
session_history / session_context 一一对应。
"""
import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    id: str
    messages: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    title: str = "新会话"
    created_at: float = 0.0
    updated_at: float = 0.0


SESSIONS: dict[str, Session] = {}
_LOCK = threading.Lock()


def create_session() -> Session:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    s = Session(id=sid, created_at=now, updated_at=now)
    with _LOCK:
        SESSIONS[sid] = s
    return s


def get_session(sid: str | None) -> Session | None:
    if not sid:
        return None
    with _LOCK:
        return SESSIONS.get(sid)


def list_sessions() -> list[Session]:
    with _LOCK:
        return sorted(SESSIONS.values(), key=lambda s: s.updated_at, reverse=True)


def delete_session(sid: str) -> bool:
    with _LOCK:
        return SESSIONS.pop(sid, None) is not None
