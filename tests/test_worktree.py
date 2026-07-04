"""runtime/worktree.py 测试 — 名称校验, 变更统计"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestValidateWorktreeName:
    def test_valid_names(self):
        from runtime.worktree import validate_worktree_name
        assert validate_worktree_name("auth-refactor") is None
        assert validate_worktree_name("my.worktree") is None
        assert validate_worktree_name("task_001") is None
        assert validate_worktree_name("a" * 64) is None

    def test_empty_rejected(self):
        from runtime.worktree import validate_worktree_name
        assert validate_worktree_name("") is not None

    def test_dot_rejected(self):
        from runtime.worktree import validate_worktree_name
        assert validate_worktree_name(".") is not None
        assert validate_worktree_name("..") is not None

    def test_spaces_rejected(self):
        from runtime.worktree import validate_worktree_name
        assert validate_worktree_name("my worktree") is not None

    def test_too_long_rejected(self):
        from runtime.worktree import validate_worktree_name
        assert validate_worktree_name("a" * 65) is not None


class TestCountWorktreeChanges:
    def test_nonexistent_path(self):
        from runtime.worktree import _count_worktree_changes
        files, commits = _count_worktree_changes(Path("/nonexistent/path/xyz"))
        assert files == -1
        assert commits == -1
