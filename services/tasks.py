"""任务系统 — s12 + s17"""
import json, time, random
from pathlib import Path
from dataclasses import dataclass, asdict
from config import safe_print,  TASKS_DIR

@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str          # pending | in_progress | completed
    owner: str | None    # 认领者（多 Agent 场景）
    blockedBy: list[str] # 依赖的任务 ID 列表
    worktree: str | None = None  # s18: 绑定的 worktree 名称
def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"
def save_task(task: Task):
    _task_path(task.id).write_text(json.dumps(asdict(task), indent=2),
                                   encoding="utf-8")
def load_task(task_id: str) -> Task:
    return Task(**json.loads(_task_path(task_id).read_text(encoding="utf-8")))
def create_task(subject: str, description: str = "",
                blockedBy: list[str] | None = None) -> Task:
    """创建任务并持久化到 .tasks/{id}.json。"""
    task = Task(
        id=f"task_{int(time.time())}_{random.randint(0, 9999):04d}",
        subject=subject,
        description=description,
        status="pending",
        owner=None,
        blockedBy=blockedBy or [],
    )
    save_task(task)
    return task
def list_tasks() -> list[Task]:
    """列出所有任务（读 .tasks/ 下所有 JSON 文件）。"""
    return [Task(**json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(TASKS_DIR.glob("task_*.json"))]
def get_task(task_id: str) -> str:
    """返回单个任务的完整 JSON。"""
    task = load_task(task_id)
    return json.dumps(asdict(task), indent=2, ensure_ascii=False)
def can_start(task_id: str) -> bool:
    """检查 blockedBy 里的所有依赖是否都 completed。
    不存在的依赖视为 blocked。"""
    task = load_task(task_id)
    for dep_id in task.blockedBy:
        if not _task_path(dep_id).exists():
            return False
        if load_task(dep_id).status != "completed":
            return False
    return True
def scan_unclaimed_tasks() -> list[dict]:
    """扫描任务板上所有可认领的任务。
    三个条件：pending + 无 owner + 所有 blockedBy 依赖已完成。
    队友在 IDLE 阶段调用此函数来发现可以主动认领的任务。"""
    unclaimed = []
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        task = json.loads(f.read_text(encoding="utf-8"))
        if (task.get("status") == "pending"
                and not task.get("owner")
                and can_start(task["id"])):
            unclaimed.append(task)
    return unclaimed
def claim_task(task_id: str, owner: str = "agent") -> str:
    """认领 pending 任务：设 owner，pending → in_progress。
    依赖未完成或已被认领则拒绝。"""
    task = load_task(task_id)
    if task.status != "pending":
        return f"任务 {task_id} 状态为 {task.status}，无法认领"
    if task.owner:
        return f"任务 {task_id} 已被 {task.owner} 认领"
    if not can_start(task_id):
        deps = [d for d in task.blockedBy
                if not _task_path(d).exists()
                or load_task(d).status != "completed"]
        return f"被阻塞，依赖未完成: {deps}"
    task.owner = owner
    task.status = "in_progress"
    save_task(task)
    safe_print(f"  \033[36m[认领] {task.subject} → in_progress (owner: {owner})\033[0m")
    return f"已认领 {task.id} ({task.subject})"
def complete_task(task_id: str) -> str:
    """完成 in_progress 任务 → completed，并扫描解锁的下游任务。"""
    task = load_task(task_id)
    if task.status != "in_progress":
        return f"任务 {task_id} 状态为 {task.status}，无法完成"
    task.status = "completed"
    save_task(task)
    # 扫描被解锁的下游任务
    unblocked = [t.subject for t in list_tasks()
                 if t.status == "pending" and t.blockedBy
                 and can_start(t.id)]
    safe_print(f"  \033[32m[完成] {task.subject} [OK]\033[0m")
    msg = f"已完成 {task.id} ({task.subject})"
    if unblocked:
        msg += f"\n已解锁: {', '.join(unblocked)}"
        safe_print(f"  \033[33m[已解锁] {', '.join(unblocked)}\033[0m")
    return msg
def run_create_task(subject: str, description: str = "",
                    blockedBy: list[str] | None = None) -> str:
    task = create_task(subject, description, blockedBy)
    deps = f" (blockedBy: {', '.join(blockedBy)})" if blockedBy else ""
    safe_print(f"  \033[34m[创建任务] {task.subject}{deps}\033[0m")
    return f"已创建 {task.id}: {task.subject}{deps}"
def run_list_tasks() -> str:
    tasks = list_tasks()
    if not tasks:
        return "暂无任务。使用 create_task 添加。"
    lines = []
    for t in tasks:
        icon = {"pending": "o", "in_progress": "*",
                "completed": "[OK]"}.get(t.status, "?")
        deps = f" (blockedBy: {', '.join(t.blockedBy)})" if t.blockedBy else ""
        owner = f" [{t.owner}]" if t.owner else ""
        wt = f" (wt:{t.worktree})" if t.worktree else ""
        lines.append(f"  {icon} {t.id}: {t.subject} "
                     f"[{t.status}]{owner}{deps}{wt}")
    return "\n".join(lines)
def run_get_task(task_id: str) -> str:
    try:
        return get_task(task_id)
    except FileNotFoundError:
        return f"错误: 任务 {task_id} 未找到"
def run_claim_task(task_id: str) -> str:
    return claim_task(task_id, owner="agent")
def run_complete_task(task_id: str) -> str:
    return complete_task(task_id)
