"""services/background.py 测试 — 慢操作判断"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestIsSlowOperation:
    def test_non_bash_returns_false(self):
        from services.background import is_slow_operation
        assert is_slow_operation("read_file", {"path": "x"}) is False

    def test_install_is_slow(self):
        from services.background import is_slow_operation
        assert is_slow_operation("bash", {"command": "pip install torch"}) is True

    def test_build_is_slow(self):
        from services.background import is_slow_operation
        assert is_slow_operation("bash", {"command": "docker build -t myapp ."}) is True

    def test_test_is_slow(self):
        from services.background import is_slow_operation
        assert is_slow_operation("bash", {"command": "pip install pytest"}) is True

    def test_echo_is_not_slow(self):
        from services.background import is_slow_operation
        assert is_slow_operation("bash", {"command": "echo hello"}) is False


class TestShouldRunBackground:
    def test_explicit_background(self):
        from services.background import should_run_background
        assert should_run_background("bash", {"command": "echo", "run_in_background": True}) is True

    def test_run_in_background_overrides(self):
        from services.background import should_run_background
        # LLM 显式传 run_in_background=true 优先，不管是不是 bash
        assert should_run_background("read_file", {"run_in_background": True}) is True
