"""通用工具函数 — terminal_print, safe_path, run_bash/read/write/edit/find, extract_text, has_tool_use, call_tool_handler, 压缩辅助函数"""
import subprocess, threading, ast, json
from pathlib import Path
from config import WORKDIR, READLINE_AVAILABLE, CURRENT_TODOS

# ── s20: terminal_print — 后台线程输出不打断用户输入 ──────
def terminal_print(text: str):
    """安全打印：后台线程输出时先清行、打印、再恢复用户正在输入的内容。
    主线程直接 print。"""
    if threading.current_thread() is threading.main_thread():
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode('ascii', errors='replace').decode('ascii'))
        return
    line = ""
    if READLINE_AVAILABLE:
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
    try:
        print(f"\r\033[K{text}")
    except UnicodeEncodeError:
        print(f"\r\033[K{text.encode('ascii', errors='replace').decode('ascii')}")
    # 始终恢复提示符（即使 line 为空），否则 cron 触发后用户看不到输入提示
    print(f"\033[36ms20 >> \033[0m{line}", end="", flush=True)

# ── 工具执行函数 ───────────────────────────────────────
def safe_path(p: str, cwd: Path = None) -> Path:
    """安全路径解析：禁止访问工作目录之外的路径。
    s18: 可选 cwd 参数，队友在 worktree 下执行时传入 worktree 路径。"""
    base = cwd or WORKDIR
    path = (base / p).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"路径越界: {p}")
    return path

def run_bash(command: str, run_in_background: bool = False,
             cwd: Path = None) -> str:
    # run_in_background 由 agent_loop 分发处理，这里只负责同步执行
    # s18: 可选 cwd 参数，队友在 worktree 下执行时传入 worktree 路径
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=cwd or WORKDIR,
            capture_output=True,
            text=True,
            encoding="utf-8", errors="replace",  # Windows GBK 兼容
            timeout=120
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（无输出）"
    except subprocess.TimeoutExpired:
        return "错误: 命令超时 (120s)"

def run_python(code: str, cwd: Path = None) -> str:
    """s21: 安全执行 Python 代码 — 写入临时文件 → 执行 → 清理。
    解决 Windows cmd.exe 下 python -c 多行脚本因引号嵌套失败的问题。"""
    import random
    tmp_dir = (cwd or WORKDIR) / ".runtime" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    script_path = tmp_dir / f"run_{random.randint(0, 99999):05d}.py"
    try:
        script_path.write_text(code, encoding="utf-8")
        r = subprocess.run(
            ["python", str(script_path)],
            cwd=cwd or WORKDIR,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（无输出）"
    except subprocess.TimeoutExpired:
        return "错误: 脚本执行超时 (120s)"
    finally:
        try:
            script_path.unlink()
        except Exception:
            pass

def run_read(path: str, limit: int | None = None, cwd: Path = None) -> str:
    """s18: 可选 cwd 参数，队友在 worktree 下读取。"""
    try:
        lines = safe_path(path, cwd).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... （还有 {len(lines) - limit} 行）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"
def run_write(path: str, content: str, cwd: Path = None) -> str:
    """s18: 可选 cwd 参数，队友在 worktree 下写入。"""
    try:
        file_path = safe_path(path, cwd)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"已写入 {len(content)} 字节到 {path}"
    except Exception as e:
        return f"错误: {e}"
def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"错误: 在 {path} 中未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"已编辑 {path}"
    except Exception as e:
        return f"错误: {e}"
def run_find(pattern: str) -> str:
    import glob as g
    try:
        results = []
        recursive = '**' in pattern
        for match in g.glob(pattern, root_dir=WORKDIR, recursive=recursive):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "（无匹配）"
    except Exception as e:
        return f"错误: {e}"
def _normalize_todos(todos):
    """校验 todo 格式：必须是列表，每项必须有 content 和 status"""
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "错误: todos 必须是列表或 JSON 数组字符串"
    if not isinstance(todos, list):
        return None, "错误: todos 必须是列表"
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return None, f"错误: todos[{i}] 必须是对象"
        if "content" not in t or "status" not in t:
            return None, f"错误: todos[{i}] 缺少 'content' 或 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return None, f"错误: todos[{i}] 状态 '{t['status']}' 无效"
    return todos, None
def run_todo_write(todos: list) -> str:
    """s05: 更新任务列表并在终端渲染看板"""
    global CURRENT_TODOS
    todos, error = _normalize_todos(todos)
    if error:
        return error
    CURRENT_TODOS = todos
    lines = ["\n\033[33m## 当前任务\033[0m"]
    for t in CURRENT_TODOS:
        icon = {"pending": " ", "in_progress": "\033[36m>\033[0m", "completed": "\033[32m[OK]\033[0m"}[t["status"]]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))
    return f"已更新 {len(CURRENT_TODOS)} 个任务"
def extract_text(content) -> str:
    """从消息内容块中提取纯文本"""
    if not isinstance(content, list):
        return str(content)
    return "\n".join(getattr(b, "text", "") for b in content
                     if getattr(b, "type", None) == "text")

def has_tool_use(content) -> bool:
    """检查响应中是否包含 tool_use 块。不依赖 stop_reason（不同 API 代理行为不同）。"""
    return any(getattr(block, "type", None) == "tool_use"
               for block in content)
def call_tool_handler(handler, args: dict, name: str) -> str:
    """安全调用工具 handler：handler 不存在或参数不匹配时返回错误消息，不抛异常。"""
    if not handler:
        return f"未知工具: {name}"
    try:
        return handler(**(args or {}))
    except TypeError as e:
        return f"参数错误: {e}"
def estimate_size(msgs):
    """估算消息列表的字符大小（非精确 token，但够用）。"""
    return len(str(msgs))
def _block_type(block):
    """获取块的 type 字段，兼容 dict 和对象两种格式。"""
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
def _message_has_tool_use(msg):
    """检查 assistant 消息是否包含 tool_use 块。"""
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(_block_type(b) == "tool_use" for b in content)
def _is_tool_result_message(msg):
    """检查 user 消息是否包含 tool_result 块。"""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result"
               for b in content)
