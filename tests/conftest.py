"""共享 fixtures：mock Anthropic client + 临时工作目录"""
import pytest
import sys
import tempfile
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def temp_workdir(monkeypatch):
    """用临时目录替代所有运行时路径，隔离文件 I/O 副作用。"""
    with tempfile.TemporaryDirectory() as tmp:
        rt = Path(tmp) / ".runtime"
        rt.mkdir()
        (rt / "tasks").mkdir()
        (rt / "mailboxes").mkdir()
        (rt / "worktrees").mkdir()
        (rt / "memory").mkdir()

        # config.py 全局路径
        monkeypatch.setattr("config.WORKDIR", Path(tmp))
        monkeypatch.setattr("config.RUNTIME_DIR", rt)
        monkeypatch.setattr("config.TASKS_DIR", rt / "tasks")
        monkeypatch.setattr("config.MEMORY_DIR", rt / "memory")
        monkeypatch.setattr("config.MEMORY_INDEX", rt / "memory" / "MEMORY.md")
        monkeypatch.setattr("config.TRANSCRIPT_DIR", rt / "transcripts")
        monkeypatch.setattr("config.TOOL_RESULTS_DIR", rt / "tool-results")
        monkeypatch.setattr("config.WORKTREES_DIR", rt / "worktrees")
        monkeypatch.setattr("config.SKILLS_DIR", Path(tmp) / "skills")

        # 跨模块常量（不在 config.py 里定义的）
        monkeypatch.setattr("runtime.bus.MAILBOX_DIR", rt / "mailboxes")
        monkeypatch.setattr("services.cron.DURABLE_PATH", rt / "scheduled_tasks.json")

        # 已 import 的模块引用也要 patch
        monkeypatch.setattr("services.memory.MEMORY_DIR", rt / "memory", raising=False)
        monkeypatch.setattr("services.memory.MEMORY_INDEX", rt / "memory" / "MEMORY.md", raising=False)

        # 已在其他模块 import 的引用也要 patch
        for mod in ["core.utils", "core.compression", "core.prompt",
                     "services.memory", "services.cron", "services.tasks",
                     "runtime.bus", "runtime.hooks", "runtime.worktree"]:
            monkeypatch.setattr(f"{mod}.WORKDIR", Path(tmp), raising=False)
            monkeypatch.setattr(f"{mod}.TASKS_DIR", rt / "tasks", raising=False)

        yield Path(tmp)


@pytest.fixture
def make_mock_response():
    """工厂函数：生成指定内容的 mock Anthropic 响应。
    用法: resp = make_mock_response(blocks=[FakeBlock("text", text="hi")])
    """

    class FakeBlock:
        def __init__(self, btype, **kw):
            self.type = btype
            for k, v in kw.items():
                setattr(self, k, v)

    class FakeResponse:
        def __init__(self, blocks, stop_reason="end_turn"):
            self.content = blocks
            self.stop_reason = stop_reason

    def _make(blocks=None, stop_reason="end_turn"):
        return FakeResponse(
            blocks or [FakeBlock("text", text="mock response")],
            stop_reason,
        )

    return _make


@pytest.fixture
def mock_client(monkeypatch, make_mock_response):
    """Mock anthropic client.messages.create，返回简短的纯文本响应。"""
    fake = type("FakeClient", (), {
        "messages": type("FakeMessages", (), {
            "create": lambda *a, **kw: make_mock_response()
        })()
    })
    monkeypatch.setattr("config.client", fake)
    return fake


@pytest.fixture(autouse=True)
def mock_lazy_imports(monkeypatch):
    """预设所有延迟导入的模块，避免 NameError。
    这些模块在 prompt.py / engine.py 等文件内用函数内 import，
    测试时需要提前 patch 好。"""
    monkeypatch.setattr("tools.builtin.BUILTIN_HANDLERS", {"bash": lambda: None}, raising=False)
    monkeypatch.setattr("tools.builtin.SUB_HANDLERS", {"bash": lambda: None}, raising=False)
    monkeypatch.setattr("tools.mcp.mcp_clients", {}, raising=False)
