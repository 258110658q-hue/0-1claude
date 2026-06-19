"""core/utils.py 测试 — safe_path, run_*, extract_text, has_tool_use, call_tool_handler, 压缩辅助"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════
# safe_path
# ═══════════════════════════════════════════════════════════
class TestSafePath:
    def test_normal_path_inside_workdir(self, temp_workdir):
        from core.utils import safe_path
        result = safe_path("foo/bar.txt")
        assert result == temp_workdir / "foo" / "bar.txt"

    def test_absolute_path_inside_workdir(self, temp_workdir):
        from core.utils import safe_path
        p = str(temp_workdir / "sub" / "file.py")
        result = safe_path(p)
        assert result == temp_workdir / "sub" / "file.py"

    def test_path_escape_raises(self, temp_workdir):
        from core.utils import safe_path
        with pytest.raises(ValueError, match="路径越界"):
            safe_path("../outside/file.txt")

    def test_dotdot_attack_raises(self, temp_workdir):
        from core.utils import safe_path
        with pytest.raises(ValueError, match="路径越界"):
            safe_path("../../etc/passwd")

    def test_cwd_parameter(self, temp_workdir):
        from core.utils import safe_path
        alt = temp_workdir / "alt"
        alt.mkdir()
        result = safe_path("test.txt", cwd=alt)
        assert result == alt / "test.txt"

    def test_cwd_escape_still_blocked(self, temp_workdir):
        from core.utils import safe_path
        alt = temp_workdir / "alt"
        alt.mkdir()
        with pytest.raises(ValueError):
            safe_path("../outside", cwd=alt)


# ═══════════════════════════════════════════════════════════
# extract_text
# ═══════════════════════════════════════════════════════════
class TestExtractText:
    def test_string_content(self):
        from core.utils import extract_text
        assert extract_text("hello") == "hello"

    def test_list_of_blocks(self):
        from core.utils import extract_text

        class Block:
            def __init__(self, btype, text=""):
                self.type = btype
                self.text = text

        blocks = [Block("text", "hello"), Block("tool_use", ""), Block("text", "world")]
        assert extract_text(blocks) == "hello\nworld"

    def test_empty_list(self):
        from core.utils import extract_text
        assert extract_text([]) == ""

    def test_no_text_blocks(self):
        from core.utils import extract_text

        class Block:
            def __init__(self, btype):
                self.type = btype

        assert extract_text([Block("tool_use")]) == ""


# ═══════════════════════════════════════════════════════════
# has_tool_use
# ═══════════════════════════════════════════════════════════
class TestHasToolUse:
    def test_has_tool_use_returns_true(self):
        from core.utils import has_tool_use

        class Block:
            def __init__(self, btype):
                self.type = btype

        content = [Block("text"), Block("tool_use"), Block("text")]
        assert has_tool_use(content) is True

    def test_pure_text_returns_false(self):
        from core.utils import has_tool_use

        class Block:
            def __init__(self, btype):
                self.type = btype

        assert has_tool_use([Block("text"), Block("text")]) is False

    def test_empty_returns_false(self):
        from core.utils import has_tool_use
        assert has_tool_use([]) is False


# ═══════════════════════════════════════════════════════════
# call_tool_handler
# ═══════════════════════════════════════════════════════════
class TestCallToolHandler:
    def test_handler_exists(self):
        from core.utils import call_tool_handler
        result = call_tool_handler(lambda x: f"got {x}", {"x": "hello"}, "test")
        assert result == "got hello"

    def test_handler_not_found(self):
        from core.utils import call_tool_handler
        result = call_tool_handler(None, {}, "missing_tool")
        assert "未知工具" in result

    def test_type_error_returns_message(self):
        from core.utils import call_tool_handler
        result = call_tool_handler(lambda x: x, {}, "bad_args")
        assert "参数错误" in result

    def test_handler_returns_empty_string(self):
        from core.utils import call_tool_handler
        result = call_tool_handler(lambda: "", {}, "empty")
        assert result == ""


# ═══════════════════════════════════════════════════════════
# estimate_size
# ═══════════════════════════════════════════════════════════
class TestEstimateSize:
    def test_empty_list(self):
        from core.utils import estimate_size
        assert estimate_size([]) > 0

    def test_single_message(self):
        from core.utils import estimate_size
        size = estimate_size([{"role": "user", "content": "hello"}])
        assert size > 10

    def test_grows_with_content(self):
        from core.utils import estimate_size
        s1 = estimate_size([{"role": "user", "content": "hi"}])
        s2 = estimate_size([{"role": "user", "content": "hi" * 100}])
        assert s2 > s1


# ═══════════════════════════════════════════════════════════
# _block_type
# ═══════════════════════════════════════════════════════════
class TestBlockType:
    def test_dict_block(self):
        from core.utils import _block_type
        assert _block_type({"type": "tool_use"}) == "tool_use"

    def test_object_block(self):
        from core.utils import _block_type

        class B:
            type = "text"

        assert _block_type(B()) == "text"

    def test_no_type_returns_none(self):
        from core.utils import _block_type
        assert _block_type({}) is None


# ═══════════════════════════════════════════════════════════
# _message_has_tool_use
# ═══════════════════════════════════════════════════════════
class TestMessageHasToolUse:
    def test_assistant_with_tool_use(self):
        from core.utils import _message_has_tool_use
        msg = {"role": "assistant", "content": [{"type": "tool_use"}, {"type": "text"}]}
        assert _message_has_tool_use(msg) is True

    def test_assistant_pure_text(self):
        from core.utils import _message_has_tool_use
        msg = {"role": "assistant", "content": [{"type": "text"}]}
        assert _message_has_tool_use(msg) is False

    def test_user_role(self):
        from core.utils import _message_has_tool_use
        msg = {"role": "user", "content": [{"type": "tool_use"}]}
        assert _message_has_tool_use(msg) is False

    def test_content_is_string(self):
        from core.utils import _message_has_tool_use
        msg = {"role": "assistant", "content": "plain text"}
        assert _message_has_tool_use(msg) is False


# ═══════════════════════════════════════════════════════════
# _is_tool_result_message
# ═══════════════════════════════════════════════════════════
class TestIsToolResultMessage:
    def test_user_with_tool_result(self):
        from core.utils import _is_tool_result_message
        msg = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "x"}]}
        assert _is_tool_result_message(msg) is True

    def test_assistant_role(self):
        from core.utils import _is_tool_result_message
        msg = {"role": "assistant", "content": [{"type": "tool_result"}]}
        assert _is_tool_result_message(msg) is False

    def test_content_is_string(self):
        from core.utils import _is_tool_result_message
        msg = {"role": "user", "content": "text"}
        assert _is_tool_result_message(msg) is False


# ═══════════════════════════════════════════════════════════
# _normalize_todos
# ═══════════════════════════════════════════════════════════
class TestNormalizeTodos:
    def test_valid_list(self):
        from core.utils import _normalize_todos
        todos, err = _normalize_todos([{"content": "task 1", "status": "pending"}])
        assert err is None
        assert len(todos) == 1

    def test_json_string(self):
        from core.utils import _normalize_todos
        todos, err = _normalize_todos('[{"content": "x", "status": "completed"}]')
        assert err is None
        assert todos[0]["status"] == "completed"

    def test_invalid_json_string(self):
        from core.utils import _normalize_todos
        _, err = _normalize_todos("not json")
        assert err is not None

    def test_not_list_returns_error(self):
        from core.utils import _normalize_todos
        _, err = _normalize_todos({"not": "a list"})
        assert err is not None

    def test_missing_status(self):
        from core.utils import _normalize_todos
        _, err = _normalize_todos([{"content": "x"}])
        assert "缺少" in err

    def test_invalid_status(self):
        from core.utils import _normalize_todos
        _, err = _normalize_todos([{"content": "x", "status": "invalid"}])
        assert "无效" in err


# ═══════════════════════════════════════════════════════════
# run_bash
# ═══════════════════════════════════════════════════════════
class TestRunBash:
    def test_echo(self, temp_workdir):
        from core.utils import run_bash
        result = run_bash("echo hello")
        assert "hello" in result

    def test_long_output_truncated(self, temp_workdir):
        from core.utils import run_bash
        result = run_bash(f"python -c \"print('x' * 60000)\"")
        assert len(result) <= 50000

    def test_timeout(self, temp_workdir, monkeypatch):
        """用 monkeypatch 把 run_bash 的 timeout 改小，避免等 120 秒"""
        import core.utils
        import subprocess as sp_mod

        orig_run = sp_mod.run

        def fake_run(*a, **kw):
            kw["timeout"] = 1  # 1 秒超时
            return orig_run(*a, **kw)

        monkeypatch.setattr(sp_mod, "run", fake_run)
        result = core.utils.run_bash("python -c \"import time; time.sleep(5)\"")
        assert "超时" in result

    def test_error_command(self, temp_workdir):
        from core.utils import run_bash
        result = run_bash("nonexistent_command_xyz")
        assert len(result) > 0  # 返回 stderr


# ═══════════════════════════════════════════════════════════
# run_read
# ═══════════════════════════════════════════════════════════
class TestRunRead:
    def test_read_file(self, temp_workdir):
        from core.utils import run_read
        (temp_workdir / "test.txt").write_text("line1\nline2\nline3", encoding="utf-8")
        result = run_read("test.txt")
        assert "line1" in result
        assert "line3" in result

    def test_file_not_found(self, temp_workdir):
        from core.utils import run_read
        result = run_read("nonexistent.txt")
        assert "错误" in result

    def test_limit(self, temp_workdir):
        from core.utils import run_read
        lines = [f"line{i}" for i in range(100)]
        (temp_workdir / "big.txt").write_text("\n".join(lines), encoding="utf-8")
        result = run_read("big.txt", limit=5)
        assert "还有" in result  # 截断提示


# ═══════════════════════════════════════════════════════════
# run_write
# ═══════════════════════════════════════════════════════════
class TestRunWrite:
    def test_write_file(self, temp_workdir):
        from core.utils import run_write
        result = run_write("out.txt", "hello world")
        assert "已写入" in result
        assert (temp_workdir / "out.txt").read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_dirs(self, temp_workdir):
        from core.utils import run_write
        result = run_write("a/b/c/file.txt", "nested")
        assert "已写入" in result
        assert (temp_workdir / "a" / "b" / "c" / "file.txt").exists()


# ═══════════════════════════════════════════════════════════
# run_edit
# ═══════════════════════════════════════════════════════════
class TestRunEdit:
    def test_replace_text(self, temp_workdir):
        from core.utils import run_edit
        (temp_workdir / "edit.txt").write_text("hello world", encoding="utf-8")
        result = run_edit("edit.txt", "world", "python")
        assert "已编辑" in result
        assert (temp_workdir / "edit.txt").read_text(encoding="utf-8") == "hello python"

    def test_text_not_found(self, temp_workdir):
        from core.utils import run_edit
        (temp_workdir / "edit.txt").write_text("hello", encoding="utf-8")
        result = run_edit("edit.txt", "xyz", "abc")
        assert "未找到" in result


# ═══════════════════════════════════════════════════════════
# run_find
# ═══════════════════════════════════════════════════════════
class TestRunFind:
    def test_match_files(self, temp_workdir):
        from core.utils import run_find
        (temp_workdir / "a.py").write_text("")
        (temp_workdir / "b.py").write_text("")
        (temp_workdir / "c.txt").write_text("")
        result = run_find("*.py")
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_no_match(self, temp_workdir):
        from core.utils import run_find
        result = run_find("*.rs")
        assert "无匹配" in result

    def test_recursive_glob(self, temp_workdir):
        from core.utils import run_find
        (temp_workdir / "subdir").mkdir()
        (temp_workdir / "subdir" / "deep.py").write_text("")
        result = run_find("**/*.py")
        assert "deep.py" in result


# ═══════════════════════════════════════════════════════════
# run_todo_write
# ═══════════════════════════════════════════════════════════
class TestRunTodoWrite:
    def test_update_todos(self):
        from core.utils import run_todo_write
        result = run_todo_write([{"content": "task A", "status": "pending"}])
        assert "已更新" in result

    def test_invalid_input_returns_error(self):
        from core.utils import run_todo_write
        result = run_todo_write("invalid")
        assert "错误" in result
