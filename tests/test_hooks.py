"""runtime/hooks.py 测试 — 钩子注册, 触发, 权限检查"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestRegisterAndTrigger:
    def setup_method(self):
        """每个测试前清空钩子，避免互相污染。"""
        from runtime.hooks import HOOKS
        for k in HOOKS:
            HOOKS[k].clear()

    def test_register_single(self):
        from runtime.hooks import HOOKS, register_hook
        register_hook("PreToolUse", lambda b: None)
        assert len(HOOKS["PreToolUse"]) == 1

    def test_trigger_all(self):
        from runtime.hooks import register_hook, trigger_hooks

        results = []

        def cb1(block):
            results.append(1)
            return None

        def cb2(block):
            results.append(2)
            return None

        register_hook("PostToolUse", cb1)
        register_hook("PostToolUse", cb2)
        trigger_hooks("PostToolUse", "test_block")
        assert results == [1, 2]

    def test_stop_on_non_none(self):
        from runtime.hooks import register_hook, trigger_hooks

        results = []

        def cb1(block):
            results.append(1)
            return "blocked"

        def cb2(block):
            results.append(2)
            return None

        register_hook("PostToolUse", cb1)
        register_hook("PostToolUse", cb2)
        result = trigger_hooks("PostToolUse", "test")
        assert result == "blocked"
        assert results == [1]

    def test_no_callbacks_returns_none(self):
        from runtime.hooks import trigger_hooks
        assert trigger_hooks("Stop") is None


class TestPermissionHook:
    def test_deny_list_blocked(self, monkeypatch):
        from runtime.hooks import permission_hook

        class Block:
            name = "bash"
            input = {"command": "rm -rf /"}

        result = permission_hook(Block())
        assert "拒绝" in result or "denied" in result.lower()

    def test_normal_bash_allowed(self, monkeypatch):
        from runtime.hooks import permission_hook

        class Block:
            name = "bash"
            input = {"command": "echo hello"}

        result = permission_hook(Block())
        assert result is None

    def test_non_bash_tool_allowed(self):
        from runtime.hooks import permission_hook

        class Block:
            name = "read_file"
            input = {"path": "test.txt"}

        result = permission_hook(Block())
        assert result is None


class TestLogHook:
    def test_returns_none(self):
        from runtime.hooks import log_hook

        class Block:
            name = "test_tool"
            input = {"arg": "value"}

        assert log_hook(Block()) is None


class TestSummaryHook:
    def test_counts_tool_results(self):
        from runtime.hooks import summary_hook
        messages = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "x"}]},
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ]
        assert summary_hook(messages) is None
