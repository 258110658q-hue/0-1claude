"""services/tasks.py 测试 — Task 数据类, CRUD, 依赖管理, 扫描认领"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestTaskDataclass:
    def test_default_values(self):
        from services.tasks import Task
        t = Task(id="1", subject="test", description="desc",
                 status="pending", owner=None, blockedBy=[])
        assert t.worktree is None  # 默认值

    def test_with_worktree(self):
        from services.tasks import Task
        t = Task(id="1", subject="t", description="d",
                 status="pending", owner=None, blockedBy=[],
                 worktree="my-wt")
        assert t.worktree == "my-wt"


class TestCreateAndListTasks:
    def test_create_task(self, temp_workdir):
        from services.tasks import create_task, list_tasks
        create_task("任务1", "描述1")
        tasks = list_tasks()
        assert len(tasks) == 1
        assert tasks[0].subject == "任务1"

    def test_create_with_dependencies(self, temp_workdir):
        from services.tasks import create_task, list_tasks
        create_task("任务A")
        create_task("任务B", blockedBy=["task_does_not_exist"])
        tasks = list_tasks()
        assert len(tasks) == 2

    def test_list_empty(self, temp_workdir):
        from services.tasks import list_tasks
        assert list_tasks() == []

    def test_get_task(self, temp_workdir):
        from services.tasks import create_task, get_task
        t = create_task("测试")
        result = get_task(t.id)
        assert t.id in result


class TestCanStart:
    def test_no_dependencies(self, temp_workdir):
        from services.tasks import create_task, can_start
        t = create_task("独立任务")
        assert can_start(t.id) is True

    def test_dependency_completed(self, temp_workdir):
        from services.tasks import create_task, can_start, claim_task, complete_task
        dep = create_task("前置任务")
        claim_task(dep.id)
        complete_task(dep.id)

        t = create_task("后续任务", blockedBy=[dep.id])
        assert can_start(t.id) is True

    def test_dependency_not_completed(self, temp_workdir):
        from services.tasks import create_task, can_start
        dep = create_task("前置任务")
        t = create_task("后续任务", blockedBy=[dep.id])
        assert can_start(t.id) is False

    def test_dependency_not_exist(self, temp_workdir):
        from services.tasks import create_task, can_start
        t = create_task("任务", blockedBy=["nonexistent"])
        assert can_start(t.id) is False


class TestClaimTask:
    def test_normal_claim(self, temp_workdir):
        from services.tasks import create_task, claim_task, load_task
        t = create_task("待认领")
        result = claim_task(t.id, owner="alice")
        assert "已认领" in result
        task = load_task(t.id)
        assert task.status == "in_progress"
        assert task.owner == "alice"

    def test_already_claimed(self, temp_workdir):
        from services.tasks import create_task, claim_task
        t = create_task("任务")
        claim_task(t.id, owner="alice")
        # 第二次认领：状态已变 in_progress，拒绝（不是 "已被认领" 而是 "状态为 in_progress"）
        result = claim_task(t.id, owner="bob")
        assert "无法认领" in result or "cannot claim" in result.lower()

    def test_wrong_status(self, temp_workdir):
        from services.tasks import create_task, claim_task, complete_task
        t = create_task("任务")
        claim_task(t.id)
        complete_task(t.id)
        result = claim_task(t.id)
        assert "无法认领" in result or "cannot claim" in result.lower()

    def test_blocked_by_incomplete(self, temp_workdir):
        from services.tasks import create_task, claim_task
        dep = create_task("前置")
        t = create_task("后续", blockedBy=[dep.id])
        result = claim_task(t.id)
        assert "阻塞" in result or "blocked" in result.lower()


class TestCompleteTask:
    def test_normal_complete(self, temp_workdir):
        from services.tasks import create_task, claim_task, complete_task, load_task
        t = create_task("任务")
        claim_task(t.id)
        result = complete_task(t.id)
        assert "已完成" in result or "Completed" in result
        assert load_task(t.id).status == "completed"

    def test_unblocks_downstream(self, temp_workdir):
        from services.tasks import (create_task, claim_task, complete_task, can_start)
        dep = create_task("前置")
        claim_task(dep.id)
        complete_task(dep.id)

        downstream = create_task("后续", blockedBy=[dep.id])
        assert can_start(downstream.id) is True

    def test_wrong_status_rejected(self, temp_workdir):
        from services.tasks import create_task, complete_task
        t = create_task("任务")
        result = complete_task(t.id)
        assert "无法完成" in result or "cannot complete" in result.lower()


class TestScanUnclaimed:
    def test_find_unclaimed(self, temp_workdir):
        from services.tasks import create_task, scan_unclaimed_tasks
        create_task("任务1")
        create_task("任务2")
        result = scan_unclaimed_tasks()
        assert len(result) == 2

    def test_claimed_excluded(self, temp_workdir):
        from services.tasks import create_task, claim_task, scan_unclaimed_tasks
        t = create_task("任务")
        claim_task(t.id, owner="alice")
        assert len(scan_unclaimed_tasks()) == 0

    def test_blocked_excluded(self, temp_workdir):
        from services.tasks import create_task, scan_unclaimed_tasks
        dep = create_task("前置")
        create_task("后续", blockedBy=[dep.id])
        assert len(scan_unclaimed_tasks()) == 1  # 只有前置可认


class TestRunHandlers:
    def test_run_create_task(self, temp_workdir):
        from services.tasks import run_create_task
        result = run_create_task("新任务", "描述")
        assert "已创建" in result or "Created" in result

    def test_run_list_tasks(self, temp_workdir):
        from services.tasks import run_list_tasks, create_task
        create_task("测试")
        result = run_list_tasks()
        assert "测试" in result

    def test_run_claim_and_complete(self, temp_workdir):
        from services.tasks import run_create_task, run_claim_task, run_complete_task
        t = run_create_task("任务")
        tid = t.split(":")[0].replace("已创建 ", "").strip()
        assert "已认领" in run_claim_task(tid)
        assert "已完成" in run_complete_task(tid)
