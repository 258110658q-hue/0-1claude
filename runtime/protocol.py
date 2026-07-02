"""协议系统 — s16"""
import time, random
from dataclasses import dataclass, field
from config import safe_print
from runtime.bus import BUS

@dataclass
class ProtocolState:
    request_id: str       # "req_004281" — 贯穿全链路的唯一编号
    type: str             # "shutdown" | "plan_approval"
    sender: str           # 发起方
    target: str           # 接收方
    status: str           # pending | approved | rejected
    payload: str          # 计划文本或关机原因
    created_at: float = field(default_factory=time.time)
pending_requests: dict[str, ProtocolState] = {}
def new_request_id() -> str:
    return f"req_{random.randint(0, 999999):06d}"
def match_response(response_type: str, request_id: str, approve: bool):
    """按 request_id 将回复关联到原请求。
    校验响应类型与请求类型匹配，防止跨类型误匹配。
    已处理的请求忽略重复回复。"""
    state = pending_requests.get(request_id)
    if not state:
        safe_print(f"  \033[31m[协议] 未知 request_id: {request_id}\033[0m")
        return
    if state.type == "shutdown" and response_type != "shutdown_response":
        safe_print(f"  \033[31m[协议] 类型不匹配: 期望 shutdown_response,"
              f" 收到 {response_type}\033[0m")
        return
    if state.type == "plan_approval" and response_type != "plan_approval_response":
        safe_print(f"  \033[31m[协议] 类型不匹配: 期望 plan_approval_response,"
              f" 收到 {response_type}\033[0m")
        return
    if state.status != "pending":
        safe_print(f"  \033[33m[协议] {request_id} 已 {state.status}，忽略重复\033[0m")
        return
    state.status = "approved" if approve else "rejected"
    icon = "[OK]" if approve else "[NO]"
    color = "32" if approve else "31"
    safe_print(f"  \033[{color}m[协议] {state.type} {icon} "
          f"({request_id}: {state.status})\033[0m")
def consume_lead_inbox(route_protocol: bool = True) -> list[dict]:
    """统一收件箱消费：先路由协议回复（match_response），再返回全部消息。
    run_check_inbox 和 _inject_inbox 都走这个入口，
    避免消息被读取但协议状态未更新的问题。"""
    msgs = BUS.read_inbox("lead")
    if not msgs:
        return []
    if route_protocol:
        for msg in msgs:
            meta = msg.get("metadata", {})
            req_id = meta.get("request_id", "")
            msg_type = msg.get("type", "")
            if req_id and msg_type.endswith("_response"):
                match_response(msg_type, req_id, meta.get("approve", False))
            # s20: 检测到 plan_approval_request 时自动批准并回复,
            # 避免依赖 LLM 理解内部协议（DeepSeek 等弱模型不会主动调 review_plan 导致死锁）。
            # 只在 status==pending 时处理, 已由 match_response 处理过的跳过。
            if msg_type == "plan_approval_request" and req_id:
                state = pending_requests.get(req_id)
                if state and state.status == "pending":
                    state.status = "approved"
                    BUS.send("lead", state.sender, "已批准（自动）。",
                             "plan_approval_response",
                             {"request_id": req_id, "approve": True})
                    safe_print(f"  \033[32m[协议] plan_approval 自动批准 "
                              f"({req_id})\033[0m")
    return msgs
