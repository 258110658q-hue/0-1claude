"""runtime/protocol.py 测试 — ProtocolState, new_request_id, match_response, consume_lead_inbox"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestProtocolState:
    def test_default_created_at(self):
        from runtime.protocol import ProtocolState
        p = ProtocolState(request_id="req_001", type="shutdown",
                          sender="lead", target="alice", status="pending", payload="")
        assert p.created_at > 0
        assert p.status == "pending"

    def test_fields(self):
        from runtime.protocol import ProtocolState
        p = ProtocolState(request_id="req_002", type="plan_approval",
                          sender="bob", target="lead", status="approved", payload="重构计划")
        assert p.sender == "bob"


class TestNewRequestId:
    def test_format(self):
        from runtime.protocol import new_request_id
        rid = new_request_id()
        assert rid.startswith("req_")

    def test_unique(self):
        from runtime.protocol import new_request_id
        ids = {new_request_id() for _ in range(100)}
        assert len(ids) == 100


class TestMatchResponse:
    def test_shutdown_match(self):
        from runtime.protocol import ProtocolState, pending_requests, match_response
        pending_requests.clear()
        pending_requests["req_001"] = ProtocolState(
            request_id="req_001", type="shutdown", sender="lead",
            target="alice", status="pending", payload="")
        match_response("shutdown_response", "req_001", approve=True)
        assert pending_requests["req_001"].status == "approved"

    def test_type_mismatch_rejected(self):
        from runtime.protocol import ProtocolState, pending_requests, match_response
        pending_requests.clear()
        pending_requests["req_001"] = ProtocolState(
            request_id="req_001", type="shutdown", sender="lead",
            target="alice", status="pending", payload="")
        match_response("plan_approval_response", "req_001", approve=True)
        assert pending_requests["req_001"].status == "pending"  # 不变

    def test_unknown_request_id(self):
        from runtime.protocol import match_response
        # 不应抛异常
        match_response("shutdown_response", "nonexistent", approve=True)

    def test_duplicate_ignored(self):
        from runtime.protocol import ProtocolState, pending_requests, match_response
        pending_requests.clear()
        pending_requests["req_001"] = ProtocolState(
            request_id="req_001", type="shutdown", sender="lead",
            target="alice", status="approved", payload="")
        match_response("shutdown_response", "req_001", approve=False)
        assert pending_requests["req_001"].status == "approved"  # 不变


class TestConsumeLeadInbox:
    def test_empty_inbox(self, temp_workdir):
        from runtime.protocol import consume_lead_inbox
        assert consume_lead_inbox() == []
