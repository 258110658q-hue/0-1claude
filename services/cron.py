"""Cron 调度系统 — s14"""
import json, time, threading, random
from datetime import datetime
from dataclasses import dataclass, asdict
from config import safe_print, RUNTIME_DIR

@dataclass
class CronJob:
    id: str
    cron: str        # 五段式: "分 时 日 月 星期"
    prompt: str      # 触发时注入给 Agent 的消息
    recurring: bool  # True=周期性, False=一次性
    durable: bool    # True=写磁盘(.scheduled_tasks.json)
DURABLE_PATH = RUNTIME_DIR / "scheduled_tasks.json"
scheduled_jobs: dict[str, CronJob] = {}   # job_id → CronJob
cron_queue: list[CronJob] = []            # 调度线程写入, agent_loop 消费
cron_lock = threading.Lock()              # 保护 scheduled_jobs + cron_queue
agent_lock = threading.Lock()             # 防止用户输入和 cron 同时跑 agent_loop
_last_fired: dict[str, str] = {}          # job_id → "YYYY-MM-DD HH:MM"
def _cron_field_matches(field: str, value: int) -> bool:
    """匹配单个 cron 字段：支持 *, */N, N, N-M, N,M,..."""
    if field == "*":
        return True
    if field.startswith("*/"):
        step = int(field[2:])
        return step > 0 and value % step == 0
    if "," in field:
        return any(_cron_field_matches(f.strip(), value)
                   for f in field.split(","))
    if "-" in field:
        lo, hi = field.split("-", 1)
        return int(lo) <= value <= int(hi)
    return value == int(field)
def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """检查五段式 cron 表达式是否匹配给定时间。
    标准 cron 语义：DOM 和 DOW 同时约束时任一匹配即可（OR）。"""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    dow_val = (dt.weekday() + 1) % 7  # Python Monday=0 → cron Sunday=0

    m = _cron_field_matches(minute, dt.minute)
    h = _cron_field_matches(hour, dt.hour)
    dom_ok = _cron_field_matches(dom, dt.day)
    month_ok = _cron_field_matches(month, dt.month)
    dow_ok = _cron_field_matches(dow, dow_val)

    if not (m and h and month_ok):
        return False
    dom_unconstrained = dom == "*"
    dow_unconstrained = dow == "*"
    if dom_unconstrained and dow_unconstrained:
        return True
    if dom_unconstrained:
        return dow_ok
    if dow_unconstrained:
        return dom_ok
    return dom_ok or dow_ok
def _validate_cron_field(field: str, lo: int, hi: int) -> str | None:
    """校验单个 cron 字段值在 [lo, hi] 范围内。"""
    if field == "*":
        return None
    if field.startswith("*/"):
        step_str = field[2:]
        if not step_str.isdigit():
            return f"无效步长: {field}"
        if int(step_str) <= 0:
            return f"步长必须 > 0: {field}"
        return None
    if "," in field:
        for part in field.split(","):
            err = _validate_cron_field(part.strip(), lo, hi)
            if err:
                return err
        return None
    if "-" in field:
        parts = field.split("-", 1)
        if not parts[0].isdigit() or not parts[1].isdigit():
            return f"无效范围: {field}"
        a, b = int(parts[0]), int(parts[1])
        if a < lo or a > hi or b < lo or b > hi:
            return f"范围 {field} 超出 [{lo}-{hi}]"
        if a > b:
            return f"范围起点 > 终点: {field}"
        return None
    if not field.isdigit():
        return f"无效字段: {field}"
    val = int(field)
    if val < lo or val > hi:
        return f"值 {val} 超出 [{lo}-{hi}]"
    return None
def validate_cron(cron_expr: str) -> str | None:
    """校验整条 cron 表达式。返回错误消息或 None。"""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return f"需要 5 个字段，实际 {len(fields)} 个"
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    names = ["分钟", "小时", "日", "月", "星期"]
    for _i, (field, (lo, hi), name) in enumerate(zip(fields, bounds, names, strict=True)):
        err = _validate_cron_field(field, lo, hi)
        if err:
            return f"{name}: {err}"
    return None
def save_durable_jobs():
    """持久化 durable 任务到 .scheduled_tasks.json。"""
    with cron_lock:
        durable = [asdict(j) for j in scheduled_jobs.values() if j.durable]
    DURABLE_PATH.write_text(json.dumps(durable, indent=2, ensure_ascii=False),
                            encoding="utf-8")
def load_durable_jobs():
    """启动时从磁盘恢复 durable 任务。跳过非法 cron 表达式。"""
    if not DURABLE_PATH.exists():
        return
    try:
        jobs = json.loads(DURABLE_PATH.read_text(encoding="utf-8"))
        for j in jobs:
            job = CronJob(**j)
            err = validate_cron(job.cron)
            if err:
                safe_print(f"  \033[31m[cron] 跳过非法任务 {job.id}: {err}\033[0m")
                continue
            scheduled_jobs[job.id] = job
        valid = [j for j in jobs if j["id"] in scheduled_jobs]
        if valid:
            safe_print(f"  \033[35m[cron] 已加载 {len(valid)} 个 durable 任务\033[0m")
    except Exception:
        pass
def schedule_job(cron: str, prompt: str, recurring: bool = True,
                 durable: bool = True) -> CronJob | str:
    """注册新的 cron 任务。先校验，再入 scheduled_jobs，durable 则写磁盘。"""
    err = validate_cron(cron)
    if err:
        return err
    # 拒绝明显不合理的一次性 cron：每分钟或每小时触发一次
    if not recurring:
        fields = cron.strip().split()
        if fields[0] == '*' and fields[1] == '*':
            return ("一次性 cron 需要指定具体分钟和小时，不能每分钟都触发。"
                    f"当前表达式 '{cron}' 会立即且反复触发。"
                    "请计算 1 分钟后的精确时刻，如现在是 14:30 就用 '31 14 * * *'")
    job = CronJob(
        id=f"cron_{random.randint(0, 999999):06d}",
        cron=cron, prompt=prompt,
        recurring=recurring, durable=durable,
    )
    with cron_lock:
        scheduled_jobs[job.id] = job
    if durable:
        save_durable_jobs()
    safe_print(f"  \033[35m[cron 注册] {job.id} '{cron}' → {prompt[:40]}\033[0m")
    return job
def cancel_job(job_id: str) -> str:
    """取消 cron 任务。durable 则更新磁盘。"""
    with cron_lock:
        job = scheduled_jobs.pop(job_id, None)
    if not job:
        return f"未找到任务 {job_id}"
    if job.durable:
        save_durable_jobs()
    safe_print(f"  \033[31m[cron 取消] {job_id}\033[0m")
    return f"已取消 {job_id}"
def cron_scheduler_loop():
    """独立 daemon 线程：每秒轮询，时间匹配的 job 塞进 cron_queue。"""
    while True:
        time.sleep(1)
        now = datetime.now()
        minute_marker = now.strftime("%Y-%m-%d %H:%M")
        need_save = False  # 延迟保存，避免在 cron_lock 内调 save_durable_jobs 死锁
        with cron_lock:
            for job in list(scheduled_jobs.values()):
                try:
                    if cron_matches(job.cron, now):
                        if _last_fired.get(job.id) != minute_marker:
                            cron_queue.append(job)
                            _last_fired[job.id] = minute_marker
                            safe_print(f"  \033[35m[cron 触发] {job.id} → "
                                  f"{job.prompt[:40]}\033[0m")
                        if not job.recurring:
                            scheduled_jobs.pop(job.id, None)
                            if job.durable:
                                need_save = True
                except Exception as e:
                    safe_print(f"  \033[31m[cron 错误] {job.id}: {e}\033[0m")
        if need_save:
            save_durable_jobs()  # 在锁外保存，避免死锁
def consume_cron_queue() -> list[CronJob]:
    """消费 cron_queue 中已触发的任务（agent_loop 调用）。"""
    with cron_lock:
        fired = list(cron_queue)
        cron_queue.clear()
    return fired
def has_cron_queue() -> bool:
    """检查是否有待交付的 cron 任务。"""
    with cron_lock:
        return bool(cron_queue)
def run_schedule_cron(cron: str, prompt: str,
                      recurring: bool = True, durable: bool = True) -> str:
    result = schedule_job(cron, prompt, recurring, durable)
    if isinstance(result, str):
        return f"错误: {result}"
    return f"已调度 {result.id}: '{cron}' → {prompt}"
def run_list_crons() -> str:
    with cron_lock:
        jobs = list(scheduled_jobs.values())
    if not jobs:
        return "暂无 cron 任务。使用 schedule_cron 添加。"
    lines = []
    for j in jobs:
        tag = "周期" if j.recurring else "一次性"
        dur = "持久化" if j.durable else "会话级"
        lines.append(f"  {j.id}: '{j.cron}' → {j.prompt[:40]} [{tag}, {dur}]")
    return "\n".join(lines)
def run_cancel_cron(job_id: str) -> str:
    return cancel_job(job_id)
