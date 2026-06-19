"""tools/mcp.py 测试 — MCPClient, normalize_mcp_name, mock servers, connect_mcp, assemble_tool_pool"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestMCPClient:
    def test_register_and_call(self):
        from tools.mcp import MCPClient
        client = MCPClient("test")
        client.register(
            [{"name": "echo", "description": "Echo tool"}],
            {"echo": lambda msg: f"echo: {msg}"}
        )
        assert client.call_tool("echo", {"msg": "hi"}) == "echo: hi"

    def test_unknown_tool(self):
        from tools.mcp import MCPClient
        client = MCPClient("test")
        client.register([], {})
        result = client.call_tool("nonexistent", {})
        assert "错误" in result or "error" in result.lower()

    def test_handler_exception(self):
        from tools.mcp import MCPClient
        client = MCPClient("test")

        def bad_handler(**kw):
            raise ValueError("oops")

        client.register([{"name": "bad"}], {"bad": bad_handler})
        result = client.call_tool("bad", {})
        assert "错误" in result or "error" in result.lower()


class TestNormalizeMcpName:
    def test_normal_name_unchanged(self):
        from tools.mcp import normalize_mcp_name
        assert normalize_mcp_name("docs_server") == "docs_server"

    def test_spaces_replaced(self):
        from tools.mcp import normalize_mcp_name
        result = normalize_mcp_name("my server")
        assert " " not in result
        assert "_" in result

    def test_special_chars_replaced(self):
        from tools.mcp import normalize_mcp_name
        result = normalize_mcp_name("bad!@#name")
        for c in "!@#":
            assert c not in result

    def test_path_traversal_normalized(self):
        from tools.mcp import normalize_mcp_name
        result = normalize_mcp_name("../../etc")
        assert "/" not in result
        assert ".." not in result


class TestMockServers:
    def test_docs_server(self):
        from tools.mcp import _mock_server_docs
        c = _mock_server_docs()
        assert len(c.tools) == 2
        names = [t["name"] for t in c.tools]
        assert "search" in names
        assert "get_version" in names

    def test_deploy_server(self):
        from tools.mcp import _mock_server_deploy
        c = _mock_server_deploy()
        names = [t["name"] for t in c.tools]
        assert "trigger" in names
        assert "status" in names


class TestConnectMcp:
    def test_connect_docs(self):
        from tools.mcp import connect_mcp, mcp_clients
        mcp_clients.clear()
        result = connect_mcp("docs")
        assert "docs" in mcp_clients
        assert "已连接" in result or "Connected" in result
        mcp_clients.clear()

    def test_already_connected(self):
        from tools.mcp import connect_mcp, mcp_clients
        mcp_clients.clear()
        connect_mcp("docs")
        result = connect_mcp("docs")
        assert "已连接" in result or "already" in result.lower()
        mcp_clients.clear()

    def test_unknown_server(self):
        from tools.mcp import connect_mcp
        result = connect_mcp("nonexistent_server_xyz")
        assert "未知" in result or "Unknown" in result.lower()


class TestAssembleToolPool:
    def test_builtin_only(self):
        from tools.mcp import assemble_tool_pool, mcp_clients
        mcp_clients.clear()
        tools, handlers = assemble_tool_pool()
        assert len(tools) > 20
        tool_names = [t["name"] for t in tools]
        assert "bash" in tool_names

    def test_with_mcp(self):
        from tools.mcp import assemble_tool_pool, connect_mcp, mcp_clients
        mcp_clients.clear()
        connect_mcp("docs")
        tools, handlers = assemble_tool_pool()
        tool_names = [t["name"] for t in tools]
        assert "mcp__docs__search" in tool_names
        assert "mcp__docs__get_version" in tool_names
        # handler 可调用
        result = handlers["mcp__docs__get_version"]()
        assert "v2.1.0" in result
        mcp_clients.clear()
