"""集成测试 — 跨模块交互验证"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAllModulesImport:
    def test_config_imports(self):
        import config

    def test_core_imports(self):
        from core import utils, prompt, compression, recovery, engine

    def test_services_imports(self):
        from services import skills, memory, tasks, cron, background

    def test_tools_imports(self):
        from tools import builtin, subagent, team, mcp

    def test_runtime_imports(self):
        from runtime import hooks, bus, protocol, teammate, worktree


class TestBuiltinHandlers:
    def test_init_handlers(self, temp_workdir):
        from tools.builtin import (
            BUILTIN_HANDLERS, SUB_HANDLERS,
            init_builtin_handlers, init_sub_handlers
        )
        # 初始化前应该是空的
        BUILTIN_HANDLERS.clear()
        SUB_HANDLERS.clear()

        init_builtin_handlers()
        init_sub_handlers()

        assert len(BUILTIN_HANDLERS) > 20
        assert len(SUB_HANDLERS) > 3
        assert "bash" in BUILTIN_HANDLERS
        assert "create_task" in BUILTIN_HANDLERS


class TestTaskPipeline:
    """完整的任务生命周期：create → claim → complete → unblock"""
    def test_full_pipeline(self, temp_workdir):
        from services.tasks import (
            create_task, claim_task, complete_task,
            can_start, list_tasks
        )
        dep = create_task("设计数据库")
        downstream = create_task("写API", blockedBy=[dep.id])

        # 依赖未完成 → 阻塞
        assert can_start(downstream.id) is False

        # 完成前置 → 解锁
        claim_task(dep.id, owner="alice")
        complete_task(dep.id)
        assert can_start(downstream.id) is True

        # 认领 + 完成后续
        claim_task(downstream.id, owner="bob")
        assert downstream.id in [t.id for t in list_tasks() if t.status == "in_progress"]
        complete_task(downstream.id)
        assert downstream.id in [t.id for t in list_tasks() if t.status == "completed"]


class TestCronPipeline:
    def test_schedule_cancel_pipeline(self, temp_workdir):
        from services.cron import (
            schedule_job, cancel_job, scheduled_jobs,
            has_cron_queue, consume_cron_queue
        )
        job = schedule_job("0 9 * * 1-5", "workday reminder", durable=False)
        assert job.id in scheduled_jobs
        cancel_job(job.id)
        assert job.id not in scheduled_jobs
        assert has_cron_queue() is False


class TestMemoryPipeline:
    def test_write_read_pipeline(self, temp_workdir):
        from services.memory import (
            write_memory_file, read_memory_index, list_memory_files
        )
        write_memory_file("test-pref", "user", "prefers tabs", "User prefers tabs over spaces.")
        idx = read_memory_index()
        assert "test-pref" in idx

        files = list_memory_files()
        assert any("test-pref" in f["name"] for f in files)
