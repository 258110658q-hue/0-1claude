"""Worktree 隔离系统 — s18"""
import json, subprocess, time, re
from pathlib import Path
from config import safe_print,  WORKDIR, WORKTREES_DIR, VALID_WT_NAME

def validate_worktree_name(name: str) -> str | None:
    """校验 worktree 名称：只允许字母数字点划线，1-64 字符。拒绝 . 和 .. """
    if not name:
        return "Worktree 名称不能为空"
    if name == "." or name == "..":
        return f"'{name}' 不是合法的 worktree 名称"
    if not VALID_WT_NAME.match(name):
        return (f"非法 worktree 名称 '{name}': "
                "只允许字母、数字、点、下划线、连字符（1-64 字符）")
    return None
def run_git(args: list[str]) -> tuple[bool, str]:
    """执行 git 命令，返回 (成功?, 输出)。"""
    try:
        r = subprocess.run(["git"] + args, cwd=WORKDIR,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=30)
        out = (r.stdout + r.stderr).strip()
        out = out[:5000] if out else "（无输出）"
        return r.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, "错误: git 超时"
def log_event(event_type: str, worktree_name: str, task_id: str = ""):
    """记录 worktree 生命周期事件到 events.jsonl。"""
    event = {"type": event_type, "worktree": worktree_name,
             "task_id": task_id, "ts": time.time()}
    events_file = WORKTREES_DIR / "events.jsonl"
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
def create_worktree(name: str, task_id: str = "") -> str:
    """创建 git worktree + 独立分支。"""
    from services.tasks import load_task  # 延迟导入
    err = validate_worktree_name(name)
    if err:
        return f"错误: {err}"
    path = WORKTREES_DIR / name
    if path.exists():
        return f"Worktree '{name}' 已存在于 {path}"
    ok, result = run_git(["worktree", "add", str(path), "-b", f"wt/{name}", "HEAD"])
    if not ok:
        return f"Git 错误: {result}"
    if task_id:
        bind_task_to_worktree(task_id, name)
    log_event("create", name, task_id)
    safe_print(f"  \033[33m[worktree] 创建: {name} @ {path}\033[0m")
    return f"Worktree '{name}' 已创建于 {path}"
def bind_task_to_worktree(task_id: str, worktree_name: str):
    """将任务绑定到 worktree。"""
    from services.tasks import load_task, save_task  # 延迟导入
    task = load_task(task_id)
    task.worktree = worktree_name
    save_task(task)
    safe_print(f"  \033[33m[绑定] {task.subject} → worktree:{worktree_name}\033[0m")
def _count_worktree_changes(path: Path) -> tuple[int, int]:
    """统计 worktree 中未提交文件数和未推送提交数。"""
    try:
        r1 = subprocess.run(["git", "status", "--porcelain"],
                            cwd=path, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=10)
        files = len([l for l in r1.stdout.strip().splitlines() if l.strip()])
        r2 = subprocess.run(["git", "log", "@{push}..HEAD", "--oneline"],
                            cwd=path, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=10)
        commits = len([l for l in r2.stdout.strip().splitlines() if l.strip()])
        return files, commits
    except Exception:
        return -1, -1
def remove_worktree(name: str, discard_changes: bool = False) -> str:
    """删除 worktree。有未提交改动时默认拒绝，需 discard_changes=true 强删。"""
    err = validate_worktree_name(name)
    if err:
        return err
    path = WORKTREES_DIR / name
    if not path.exists():
        return f"Worktree '{name}' 未找到"
    if not discard_changes:
        files, commits = _count_worktree_changes(path)
        if files < 0:
            return (f"无法验证 worktree '{name}' 状态。"
                    "使用 discard_changes=true 强制删除。")
        if files > 0 or commits > 0:
            return (f"Worktree '{name}' 有 {files} 个未提交文件 "
                    f"和 {commits} 个未推送提交。"
                    "使用 discard_changes=true 强制删除，"
                    "或 keep_worktree 保留供 review。")
    ok1, _ = run_git(["worktree", "remove", str(path), "--force"])
    if not ok1:
        return f"删除 worktree 目录失败: '{name}'"
    run_git(["branch", "-D", f"wt/{name}"])
    log_event("remove", name)
    safe_print(f"  \033[33m[worktree] 已删除: {name}\033[0m")
    return f"Worktree '{name}' 已删除"
def keep_worktree(name: str) -> str:
    """保留 worktree 分支供人工 review 后合并。"""
    err = validate_worktree_name(name)
    if err:
        return err
    log_event("keep", name)
    safe_print(f"  \033[36m[worktree] 已保留: {name}\033[0m")
    return f"Worktree '{name}' 已保留供 review（分支: wt/{name}）"
