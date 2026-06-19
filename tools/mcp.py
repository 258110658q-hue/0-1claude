"""MCP 插件系统 — s19"""
import re
from config import safe_print
from tools.builtin import BUILTIN_TOOLS, BUILTIN_HANDLERS

class MCPClient:
    """MCP 客户端：模拟 tools/list（服务发现）和 tools/call（远程调用）。
    教学版用 Python 函数模拟 server；真实 CC 通过子进程 stdin/stdout 发 JSON-RPC。"""

    def __init__(self, name: str):
        self.name = name
        self.tools: list[dict] = []           # 从 server 发现的工具列表
        self._handlers: dict[str, callable] = {}  # 工具名 → 处理函数

    def register(self, tool_defs: list[dict],
                 handlers: dict[str, callable]):
        """模拟 tools/list：注册这个 server 提供的工具和对应处理器。"""
        self.tools = tool_defs
        self._handlers = handlers

    def call_tool(self, tool_name: str, args: dict) -> str:
        """模拟 tools/call：调用 server 上的工具并返回结果。"""
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"MCP 错误: 未知工具 '{tool_name}'"
        try:
            return handler(**args)
        except Exception as e:
            return f"MCP 错误: {e}"
mcp_clients: dict[str, MCPClient] = {}   # server_name → MCPClient
_DISALLOWED_CHARS = re.compile(r'[^a-zA-Z0-9_-]')
def normalize_mcp_name(name: str) -> str:
    """规范化 MCP server/工具 名称：非 [a-zA-Z0-9_-] 的字符替换为 _。
    防止特殊字符导致命名冲突或注入。"""
    return _DISALLOWED_CHARS.sub('_', name)
def _mock_server_docs():
    """模拟「文档知识库」MCP server。"""
    client = MCPClient("docs")
    client.register(
        tool_defs=[
            {"name": "search", "description": "搜索文档。 (readOnly)",
             "inputSchema": {"type": "object",
                             "properties": {"query": {"type": "string"}},
                             "required": ["query"]}},
            {"name": "get_version", "description": "获取 API 版本。 (readOnly)",
             "inputSchema": {"type": "object", "properties": {},
                             "required": []}},
        ],
        handlers={
            "search": lambda query: f"[docs] 找到 3 条关于 '{query}' 的结果",
            "get_version": lambda: "[docs] API v2.1.0",
        })
    return client
def _mock_server_deploy():
    """模拟「部署系统」MCP server。"""
    client = MCPClient("deploy")
    client.register(
        tool_defs=[
            {"name": "trigger",
             "description": "触发部署。 (destructive — 真实 CC 需要权限确认)",
             "inputSchema": {"type": "object",
                             "properties": {"service": {"type": "string"}},
                             "required": ["service"]}},
            {"name": "status", "description": "查看部署状态。 (readOnly)",
             "inputSchema": {"type": "object",
                             "properties": {"service": {"type": "string"}},
                             "required": ["service"]}},
        ],
        handlers={
            "trigger": lambda service: f"[deploy] 已触发: {service}",
            "status": lambda service: f"[deploy] {service}: 运行中 (v1.4.2)",
        })
    return client
MOCK_SERVERS = {
    "docs": _mock_server_docs,
    "deploy": _mock_server_deploy,
}
def connect_mcp(name: str) -> str:
    """连接到 MCP server，发现其工具并加入全局 mcp_clients。
    连接后 assemble_tool_pool 会动态追加 mcp__{server}__{tool} 工具。"""
    if name in mcp_clients:
        return f"MCP server '{name}' 已连接"
    factory = MOCK_SERVERS.get(name)
    if not factory:
        available = ", ".join(MOCK_SERVERS.keys())
        return f"未知 server '{name}'。可用: {available}"
    mcp_client = factory()
    mcp_clients[name] = mcp_client
    tool_names = [t["name"] for t in mcp_client.tools]
    safe_print(f"  \033[31m[mcp] 已连接: {name} → {tool_names}\033[0m")
    return (f"已连接 MCP server '{name}'。"
            f"发现 {len(mcp_client.tools)} 个工具: {', '.join(tool_names)}")
def assemble_tool_pool() -> tuple[list[dict], dict]:
    """动态组装工具池：内置工具 + 所有已连接 MCP server 的工具。
    MCP 工具以 mcp__{server}__{tool} 命名，避免不同 server 间冲突。
    每次调用都重新构建——connect_mcp 后工具池变化，缓存会过时。"""
    tools = list(BUILTIN_TOOLS)
    handlers = dict(BUILTIN_HANDLERS)
    for server_name, mcp_client in mcp_clients.items():
        safe_server = normalize_mcp_name(server_name)
        for tool_def in mcp_client.tools:
            safe_tool = normalize_mcp_name(tool_def["name"])
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            tools.append({
                "name": prefixed,
                "description": tool_def.get("description", ""),
                "input_schema": tool_def.get("inputSchema", {}),
            })
            # 闭包默认参数绑定当前的 mcp_client 和 tool_name
            handlers[prefixed] = (
                lambda *, c=mcp_client, t=tool_def["name"], **kw:
                    c.call_tool(t, kw))
    return tools, handlers
