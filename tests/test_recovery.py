"""core/recovery.py 测试 — RecoveryState, retry_delay, is_prompt_too_long_error, with_retry"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestRecoveryState:
    def test_initial_values(self):
        from core.recovery import RecoveryState
        s = RecoveryState()
        assert s.has_escalated is False
        assert s.recovery_count == 0
        assert s.consecutive_529 == 0
        assert s.has_attempted_reactive_compact is False

    def test_fields_mutable(self):
        from core.recovery import RecoveryState
        s = RecoveryState()
        s.has_escalated = True
        assert s.has_escalated is True


class TestRetryDelay:
    def test_first_attempt(self):
        from core.recovery import retry_delay
        delay = retry_delay(0)
        assert 0.4 < delay < 1.0  # 500ms + 0~25% jitter

    def test_fifth_attempt(self):
        from core.recovery import retry_delay
        delay = retry_delay(5)
        assert 10 < delay < 32  # ~16s + jitter, capped at 32s

    def test_retry_after_header_priority(self):
        from core.recovery import retry_delay
        delay = retry_delay(0, retry_after=3.0)
        assert delay == 3.0

    def test_capped_at_32_seconds(self):
        from core.recovery import retry_delay
        for i in range(10, 20):
            # base capped at 32s + up to 25% jitter = max ~40s
            assert retry_delay(i) <= 40.0


class TestIsPromptTooLongError:
    def test_prompt_is_too_long_text(self):
        from core.recovery import is_prompt_too_long_error
        assert is_prompt_too_long_error(Exception("prompt is too long")) is True

    def test_prompt_is_too_long_underscore(self):
        from core.recovery import is_prompt_too_long_error
        assert is_prompt_too_long_error(Exception("prompt_is_too_long error")) is True

    def test_context_length_exceeded(self):
        from core.recovery import is_prompt_too_long_error
        assert is_prompt_too_long_error(Exception("context_length_exceeded")) is True

    def test_max_context_window(self):
        from core.recovery import is_prompt_too_long_error
        assert is_prompt_too_long_error(Exception("max_context_window exceeded")) is True

    def test_normal_error_not_matched(self):
        from core.recovery import is_prompt_too_long_error
        assert is_prompt_too_long_error(Exception("something else")) is False


class TestWithRetry:
    def test_success_first_try(self):
        from core.recovery import with_retry, RecoveryState
        result = with_retry(lambda: "ok", RecoveryState())
        assert result == "ok"

    def test_429_retry_then_succeed(self, monkeypatch):
        from core.recovery import with_retry, RecoveryState

        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("429 RateLimit exceeded")
            return "recovered"

        # Mock time.sleep to avoid waiting
        monkeypatch.setattr("time.sleep", lambda x: None)

        result = with_retry(flaky, RecoveryState())
        assert result == "recovered"
        assert call_count[0] == 3

    def test_529_switches_model(self, monkeypatch):
        from core.recovery import with_retry, RecoveryState

        call_count = [0]

        def overloaded():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("529 Overloaded")
            return "ok"

        monkeypatch.setattr("time.sleep", lambda x: None)
        state = RecoveryState()
        state.current_model = "primary-model"

        result = with_retry(overloaded, state)
        assert result == "ok"
        assert state.consecutive_529 == 0  # reset after success

    def test_non_transient_error_raises_immediately(self):
        from core.recovery import with_retry, RecoveryState

        def bad():
            raise ValueError("something went wrong")

        with pytest.raises(ValueError):
            with_retry(bad, RecoveryState())

    def test_max_retries_exceeded(self, monkeypatch):
        from core.recovery import with_retry, RecoveryState
        monkeypatch.setattr("time.sleep", lambda x: None)

        def always_fail():
            raise Exception("429 RateLimit")

        with pytest.raises(RuntimeError, match="超过最大重试"):
            with_retry(always_fail, RecoveryState())
