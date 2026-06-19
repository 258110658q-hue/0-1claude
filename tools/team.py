"""团队/worktree/MCP handler — 全部延迟导入避免循环依赖"""
from config import safe_print,  WORKDIR

def run_spawn_teammate(name: str, role: str, prompt: str) -> str:
    from runtime.teammate import spawn_teammate_thread
    return spawn_teammate_thread(name, role, prompt)

def run_send_message(to: str, content: str) -> str:
    from runtime.bus import BUS
    BUS.send("lead", to, content)
    return f"已发送给 {to}"

def run_check_inbox() -> str:
    from runtime.protocol import consume_lead_inbox
    msgs = consume_lead_inbox(route_protocol=True)
    if not msgs:
        return "（收件箱为空）"
    lines = []
    for m in msgs:
        meta = m.get("metadata", {})
        req_id = meta.get("request_id", "")
        tag = f" [{m['type']} req:{req_id}]" if req_id else f" [{m['type']}]"
        lines.append(f"  [{m['from']}]{tag} {m['content'][:200]}")
    return "\n".join(lines)

def run_request_shutdown(teammate: str) -> str:
    from runtime.protocol import pending_requests, new_request_id, ProtocolState
    from runtime.bus import BUS
    req_id = new_request_id()
    pending_requests[req_id] = ProtocolState(
        request_id=req_id, type="shutdown",
        sender="lead", target=teammate,
        status="pending", payload="")
    BUS.send("lead", teammate, "请收尾后关机。", "shutdown_request",
             {"request_id": req_id})
    safe_print(f"  \033[35m[协议] shutdown_request → {teammate} ({req_id})\033[0m")
    return f"已向 {teammate} 发送关机请求 (req: {req_id})"

def run_request_plan(teammate: str, task: str) -> str:
    from runtime.bus import BUS
    BUS.send("lead", teammate, f"请为以下任务提交计划: {task}", "message")
    return f"已要求 {teammate} 提交计划"

def run_review_plan(request_id: str, approve: bool, feedback: str = "") -> str:
    from runtime.protocol import pending_requests
    from runtime.bus import BUS
    state = pending_requests.get(request_id)
    if not state:
        return f"未找到请求 {request_id}"
    if state.status != "pending":
        return f"请求 {request_id} 已 {state.status}"
    state.status = "approved" if approve else "rejected"
    BUS.send("lead", state.sender,
             feedback or ("已批准" if approve else "已拒绝"),
             "plan_approval_response",
             {"request_id": request_id, "approve": approve})
    icon = "[OK]" if approve else "[NO]"
    safe_print(f"  \033[32m[协议] 计划 {icon} ({request_id})\033[0m")
    return f"计划已{'批准' if approve else '拒绝'} ({request_id})"

def run_create_worktree(name: str, task_id: str = "") -> str:
    from runtime.worktree import create_worktree
    return create_worktree(name, task_id)

def run_remove_worktree(name: str, discard_changes: bool = False) -> str:
    from runtime.worktree import remove_worktree
    return remove_worktree(name, discard_changes)

def run_keep_worktree(name: str) -> str:
    from runtime.worktree import keep_worktree
    return keep_worktree(name)

def run_connect_mcp(name: str) -> str:
    from tools.mcp import connect_mcp
    return connect_mcp(name)
