"""runtime/bus.py 测试 — MessageBus send/read"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestMessageBus:
    def test_send_and_read(self, temp_workdir):
        from runtime.bus import MessageBus, MAILBOX_DIR
        bus = MessageBus()
        bus.send("lead", "alice", "hello", "message")
        msgs = bus.read_inbox("alice")
        assert len(msgs) == 1
        assert msgs[0]["from"] == "lead"
        assert msgs[0]["content"] == "hello"

    def test_read_consumes(self, temp_workdir):
        from runtime.bus import MessageBus
        bus = MessageBus()
        bus.send("alice", "bob", "msg1")
        bus.read_inbox("bob")
        assert bus.read_inbox("bob") == []  # 已消费

    def test_read_empty_inbox(self, temp_workdir):
        from runtime.bus import MessageBus
        bus = MessageBus()
        assert bus.read_inbox("nonexistent") == []

    def test_metadata_field(self, temp_workdir):
        from runtime.bus import MessageBus
        bus = MessageBus()
        bus.send("lead", "alice", "test", "shutdown_request",
                 metadata={"request_id": "req_001", "approve": True})
        msgs = bus.read_inbox("alice")
        assert msgs[0]["metadata"]["request_id"] == "req_001"

    def test_BUS_singleton(self, temp_workdir):
        from runtime.bus import BUS
        from runtime.bus import BUS as BUS2
        assert BUS is BUS2
