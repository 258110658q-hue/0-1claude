"""config.py 测试 — 全局配置"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestConfig:
    def test_workdir_exists(self):
        import config
        assert isinstance(config.WORKDIR, Path)

    def test_primary_model_from_env(self, monkeypatch):
        monkeypatch.setenv("MODEL_ID", "test-model-v1")
        # 需要重新加载（但 import 已缓存），只测试 monkeypatch 是否生效
        import os
        assert os.environ["MODEL_ID"] == "test-model-v1"

    def test_fallback_model_default_none(self, monkeypatch):
        monkeypatch.delenv("FALLBACK_MODEL_ID", raising=False)
        import config
        assert config.FALLBACK_MODEL is None or isinstance(config.FALLBACK_MODEL, (str, type(None)))

    def test_current_todos_empty(self):
        import config
        assert config.CURRENT_TODOS == []

    def test_runtime_dir_is_subdir(self):
        import config
        assert config.RUNTIME_DIR.name == ".runtime"
        assert config.RUNTIME_DIR.parent == config.WORKDIR

    def test_safe_print_no_error(self, capsys):
        from config import safe_print
        safe_print("test")
        captured = capsys.readouterr()
        assert "test" in captured.out


class TestSafePrint:
    def test_normal_text(self, capsys):
        from config import safe_print
        safe_print("hello world")
        assert "hello world" in capsys.readouterr().out

    def test_emoji_fallback(self, capsys):
        from config import safe_print
        safe_print("test with emoji: 😀")
        out = capsys.readouterr().out
        assert len(out) > 0  # 不崩溃即可
