"""后台任务系统 — s13"""
import threading
from config import safe_print
from core.utils import call_tool_handler

_bg_counter = 0
background_tasks: dict[str, dict] = {}   # bg_id → {tool_use_id, command, status}
background_results: dict[str, str] = {}   # bg_id → output
background_lock = threading.Lock()
def is_slow_operation(tool_name: str, tool_input: dict) -> bool:
    """关键词启发式兜底：命令包含 install/build/test 等视为慢操作。"""
    if tool_name != "bash":
        return False
    cmd = tool_input.get("command", "").lower()
    slow_keywords = ["pip install", "npm install", "cargo build",
                     "docker build", "docker compose", "apt-get",
                     "brew install", "make install", "make build",
                     "git clone", "git lfs pull", "cmake", "bundle install"]
    return any(kw in cmd for kw in slow_keywords)
def should_run_background(tool_name: str, tool_input: dict) -> bool:
    """LLM 显式请求优先；未指定时用启发式兜底。"""
    if tool_input.get("run_in_background"):
        return True
    return is_slow_operation(tool_name, tool_input)
def start_background_task(block, handlers: dict) -> str:
    """将工具调用包装成 daemon 线程执行，返回 bg_id。"""
    from runtime.hooks import trigger_hooks  # 延迟导入避免循环
    global _bg_counter
    _bg_counter += 1
    bg_id = f"bg_{_bg_counter:04d}"
    cmd = block.input.get("command", block.name)

    def worker():
        handler = handlers.get(block.name)
        result = call_tool_handler(handler, block.input, block.name)
        trigger_hooks("PostToolUse", block, result)
        with background_lock:
            background_tasks[bg_id]["status"] = "completed"
            background_results[bg_id] = result
        # 实时通知：不等下一轮 agent_loop，直接打印到终端
        from core.utils import terminal_print
        summary = str(result)[:200] if len(str(result)) > 200 else str(result)
        terminal_print(f"  \033[32m[后台完成] {bg_id}: {cmd[:40]} → {summary}\033[0m")

    with background_lock:
        background_tasks[bg_id] = {
            "tool_use_id": block.id,
            "command": cmd,
            "status": "running",
        }
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    safe_print(f"  \033[33m[后台] 已派发 {bg_id}: {cmd[:40]}\033[0m")
    return bg_id
def collect_background_results() -> list[str]:
    """收集已完成的后台任务，格式化为 <task_notification>。"""
    with background_lock:
        ready_ids = [bid for bid, t in background_tasks.items()
                     if t["status"] == "completed"]
    notifications = []
    for bg_id in ready_ids:
        with background_lock:
            task = background_tasks.pop(bg_id)
            output = background_results.pop(bg_id, "")
        summary = output[:200] if len(output) > 200 else output
        notifications.append(
            f"<task_notification>\n"
            f"  <task_id>{bg_id}</task_id>\n"
            f"  <status>completed</status>\n"
            f"  <command>{task['command']}</command>\n"
            f"  <summary>{summary}</summary>\n"
            f"</task_notification>")
        safe_print(f"  \033[32m[后台完成] {bg_id}: "
              f"{task['command'][:40]} ({len(output)} 字符)\033[0m")
    return notifications
