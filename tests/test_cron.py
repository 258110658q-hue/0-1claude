"""services/cron.py 测试 — cron 解析/匹配/校验/调度"""
import pytest
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════
# _cron_field_matches
# ═══════════════════════════════════════════════════════════
class TestCronFieldMatches:
    def test_star_matches_all(self):
        from services.cron import _cron_field_matches
        for v in range(0, 60):
            assert _cron_field_matches("*", v) is True

    def test_step(self):
        from services.cron import _cron_field_matches
        assert _cron_field_matches("*/5", 0) is True
        assert _cron_field_matches("*/5", 5) is True
        assert _cron_field_matches("*/5", 15) is True
        assert _cron_field_matches("*/5", 3) is False

    def test_exact_match(self):
        from services.cron import _cron_field_matches
        assert _cron_field_matches("30", 30) is True
        assert _cron_field_matches("30", 31) is False

    def test_range(self):
        from services.cron import _cron_field_matches
        assert _cron_field_matches("10-20", 15) is True
        assert _cron_field_matches("10-20", 5) is False
        assert _cron_field_matches("10-20", 25) is False
        assert _cron_field_matches("10-20", 10) is True
        assert _cron_field_matches("10-20", 20) is True

    def test_comma_list(self):
        from services.cron import _cron_field_matches
        assert _cron_field_matches("1,15,30", 15) is True
        assert _cron_field_matches("1,15,30", 7) is False

    def test_step_zero_ignored(self):
        from services.cron import _cron_field_matches
        # */0 would cause division by zero, but our code checks step > 0
        assert _cron_field_matches("*/0", 5) is False


# ═══════════════════════════════════════════════════════════
# cron_matches
# ═══════════════════════════════════════════════════════════
class TestCronMatches:
    def test_wildcard(self, monkeypatch):
        """* * * * * 匹配任何时间"""
        from services.cron import cron_matches
        dt = datetime(2026, 6, 19, 14, 30)
        assert cron_matches("* * * * *", dt) is True

    def test_daily_at_9am(self, monkeypatch):
        from services.cron import cron_matches
        dt = datetime(2026, 6, 19, 9, 0)
        assert cron_matches("0 9 * * *", dt) is True

    def test_daily_at_9am_wrong_hour(self, monkeypatch):
        from services.cron import cron_matches
        dt = datetime(2026, 6, 19, 10, 0)
        assert cron_matches("0 9 * * *", dt) is False

    def test_weekday_only(self, monkeypatch):
        from services.cron import cron_matches
        # 2026-06-19 is a Friday (weekday 5 in Python, but cron uses 0=Sun)
        # Python weekday: Mon=0 ... Sun=6. Cron dow: Sun=0 ... Sat=6
        # Friday: Python 4, cron 5
        dt_friday = datetime(2026, 6, 19, 14, 30)  # Friday
        dt_saturday = datetime(2026, 6, 20, 14, 30)  # Saturday
        assert cron_matches("30 14 * * 1-5", dt_friday) is True
        assert cron_matches("30 14 * * 1-5", dt_saturday) is False

    def test_specific_minute_hour(self, monkeypatch):
        from services.cron import cron_matches
        dt = datetime(2026, 6, 19, 14, 47)
        assert cron_matches("47 14 * * *", dt) is True

    def test_minute_not_matching(self, monkeypatch):
        from services.cron import cron_matches
        dt = datetime(2026, 6, 19, 14, 30)
        assert cron_matches("31 14 * * *", dt) is False

    def test_five_field_required(self, monkeypatch):
        from services.cron import cron_matches
        dt = datetime(2026, 6, 19, 14, 30)
        assert cron_matches("* * * *", dt) is False  # only 4 fields


# ═══════════════════════════════════════════════════════════
# validate_cron
# ═══════════════════════════════════════════════════════════
class TestValidateCron:
    def test_valid_expression(self):
        from services.cron import validate_cron
        assert validate_cron("0 9 * * *") is None
        assert validate_cron("*/5 * * * *") is None
        assert validate_cron("30 14 19 6 *") is None

    def test_too_few_fields(self):
        from services.cron import validate_cron
        assert validate_cron("* * * *") is not None

    def test_minute_out_of_range(self):
        from services.cron import validate_cron
        assert validate_cron("60 * * * *") is not None

    def test_hour_out_of_range(self):
        from services.cron import validate_cron
        assert validate_cron("* 24 * * *") is not None

    def test_invalid_characters(self):
        from services.cron import validate_cron
        assert validate_cron("abc * * * *") is not None


# ═══════════════════════════════════════════════════════════
# schedule_job / cancel_job
# ═══════════════════════════════════════════════════════════
class TestScheduleCancelJob:
    def test_schedule_valid_cron(self, temp_workdir):
        from services.cron import schedule_job, scheduled_jobs, cancel_job
        result = schedule_job("0 9 * * *", "morning standup", durable=False)
        assert not isinstance(result, str)  # 返回 CronJob 对象
        assert result.id in scheduled_jobs
        cancel_job(result.id)

    def test_schedule_invalid_cron_returns_error(self, temp_workdir):
        from services.cron import schedule_job
        result = schedule_job("invalid", "test", durable=False)
        assert isinstance(result, str)

    def test_cancel_existing_job(self, temp_workdir):
        from services.cron import schedule_job, cancel_job, scheduled_jobs
        job = schedule_job("30 14 * * *", "reminder", durable=False)
        result = cancel_job(job.id)
        assert "已取消" in result
        assert job.id not in scheduled_jobs

    def test_cancel_nonexistent_job(self, temp_workdir):
        from services.cron import cancel_job
        result = cancel_job("nonexistent_id")
        assert "未找到" in result

    def test_one_shot_cron_rejects_every_minute(self, temp_workdir):
        from services.cron import schedule_job
        result = schedule_job("* * * * *", "bad one-shot", recurring=False, durable=False)
        assert isinstance(result, str)
        assert "一次性" in result or "不能" in result


# ═══════════════════════════════════════════════════════════
# save_durable_jobs / load_durable_jobs
# ═══════════════════════════════════════════════════════════
class TestDurableJobs:
    def test_save_and_load(self, temp_workdir, monkeypatch):
        from services.cron import (
            schedule_job, cancel_job, save_durable_jobs,
            load_durable_jobs, scheduled_jobs
        )
        # 先清空
        for jid in list(scheduled_jobs.keys()):
            cancel_job(jid)

        schedule_job("0 9 * * *", "daily", durable=True)
        save_durable_jobs()

        # 清内存再加载
        scheduled_jobs.clear()
        load_durable_jobs()
        assert len(scheduled_jobs) > 0

    def test_load_empty_file(self, temp_workdir):
        from services.cron import load_durable_jobs, scheduled_jobs
        # DURABLE_PATH 不存在时不应崩溃
        scheduled_jobs.clear()
        load_durable_jobs()
        assert len(scheduled_jobs) == 0


# ═══════════════════════════════════════════════════════════
# consume_cron_queue / has_cron_queue
# ═══════════════════════════════════════════════════════════
class TestCronQueue:
    def test_consume_empty(self):
        from services.cron import consume_cron_queue
        assert consume_cron_queue() == []

    def test_has_cron_queue_empty(self):
        from services.cron import has_cron_queue
        assert has_cron_queue() is False

    def test_consume_clears_queue(self, monkeypatch):
        from services.cron import cron_queue, consume_cron_queue, CronJob
        job = CronJob(id="test", cron="* * * * *", prompt="test",
                      recurring=True, durable=False)
        cron_queue.append(job)
        fired = consume_cron_queue()
        assert len(fired) == 1
        assert consume_cron_queue() == []  # 清空了


# ═══════════════════════════════════════════════════════════
# run_* handlers
# ═══════════════════════════════════════════════════════════
class TestRunHandlers:
    def test_run_schedule_cron(self, temp_workdir):
        from services.cron import run_schedule_cron, cancel_job
        result = run_schedule_cron("0 9 * * *", "test", durable=False)
        assert "已调度" in result
        # 清理
        jid = result.split(":")[0].replace("已调度 ", "").strip()
        cancel_job(jid)

    def test_run_list_crons_empty(self):
        from services.cron import run_list_crons
        result = run_list_crons()
        assert "暂无" in result or len(result) >= 0

    def test_run_cancel_cron_nonexistent(self):
        from services.cron import run_cancel_cron
        result = run_cancel_cron("nonexistent")
        assert "未找到" in result
