"""钩子系统 — s04"""
from config import WORKDIR

def _print(*args, **kwargs):
    """安全打印：Windows GBK 终端兼容。"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        import sys
        safe_args = [str(a).encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii') for a in args]
        print(*safe_args, **kwargs)

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}
def register_hook(event: str, callback):
    """注册钩子：把回调函数绑定到指定事件上"""
    HOOKS[event].append(callback)
def trigger_hooks(event: str, *args):
    """触发钩子：依次调用该事件的所有回调。任一返回非 None 就阻断后续。"""
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]
def permission_hook(block):
    """PreToolUse: 三级权限检查 — 拒绝列表 → 危险操作 → 用户确认"""
    if block.name == "bash":
        for pattern in DENY_LIST:
            if pattern in block.input.get("command", ""):
                _print(f"\n\033[31m[X] 已阻止: '{pattern}'\033[0m")
                return "权限拒绝: 命中拒绝列表"
        for kw in DESTRUCTIVE:
            if kw in block.input.get("command", ""):
                _print(f"\n\033[33m[!]  潜在危险命令\033[0m")
                _print(f"   工具: {block.name}({block.input})")
                choice = input("   允许执行? [y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "权限拒绝: 用户不同意"
    if block.name in ("write_file", "edit_file"):
        path = block.input.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            _print(f"\n\033[33m[!]  写入工作目录之外\033[0m")
            _print(f"   工具: {block.name}({block.input})")
            choice = input("   允许写入? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限拒绝: 用户不同意"
    # s20: MCP 外部工具的权限检查 — 部署类工具需用户确认
    if block.name.startswith("mcp__") and "deploy" in block.name:
        _print(f"\n\033[33m[权限] MCP 部署类工具: {block.name}\033[0m")
        choice = input("   允许执行? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "权限拒绝: 用户不同意"
    return None
def log_hook(block):
    """PreToolUse: 记录每次工具调用"""
    args_preview = str(list(block.input.values())[:2])[:60]
    _print(f"\033[90m[钩子] {block.name}({args_preview})\033[0m")
    return None
def large_output_hook(block, output):
    """PostToolUse: 输出过大时发出警告"""
    if len(str(output)) > 100000:
        _print(f"\033[33m[钩子] [!] {block.name} 输出过大: {len(str(output))} 字符\033[0m")
    return None
def context_inject_hook(query: str):
    """UserPromptSubmit: 用户输入前记录工作目录"""
    _print(f"\033[90m[钩子] 用户输入: 工作目录 {WORKDIR}\033[0m")
    return None
def summary_hook(messages: list):
    """Stop: 会话结束时打印工具调用统计"""
    tool_count = sum(1 for m in messages
                     for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    _print(f"\033[90m[钩子] 会话结束: 共调用 {tool_count} 次工具\033[0m")
    return None
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)
