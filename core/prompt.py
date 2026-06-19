"""System Prompt 组装"""
import json
from datetime import datetime
from config import WORKDIR, MEMORY_INDEX

PROMPT_SECTIONS = {
    "identity": f"你是在 {WORKDIR} 工作的编程智能体。",
    "memory_instruction": "相关记忆会在每轮自动注入。当用户说'记住'或表达明确偏好时，提取为记忆。",
    "skills_instruction": "需要时使用 load_skill 获取技能的完整内容。",
    "mcp_instruction": "使用 connect_mcp 连接外部 MCP server。连接后 MCP 工具以 mcp__{server}__{tool} 格式可用。",
}
def assemble_system_prompt(context: dict) -> str:
    from tools.mcp import mcp_clients  # 延迟导入避免循环
    """根据 context 真实状态按需拼接 prompt 段落。
    s19: 动态添加已连接的 MCP server 列表。"""
    sections = [PROMPT_SECTIONS["identity"]]

    # 始终加载：技能目录（扫描结果已在 context 中）
    skills_catalog = context.get("skills_catalog", "")
    if skills_catalog:
        sections.append(f"可用技能：\n{skills_catalog}")
    sections.append(PROMPT_SECTIONS["skills_instruction"])

    # 按需加载：MEMORY.md 有内容才加记忆段落
    memories = context.get("memories", "")
    if memories:
        sections.append(f"可用记忆：\n{memories}")
    sections.append(PROMPT_SECTIONS["memory_instruction"])

    # s19: MCP — 已连接的 server 列表
    sections.append(PROMPT_SECTIONS["mcp_instruction"])
    mcp_names = list(mcp_clients.keys())
    if mcp_names:
        sections.append(f"已连接的 MCP server: {', '.join(mcp_names)}")

    return "\n\n".join(sections)
_last_context_key = None
_last_prompt = None
def get_system_prompt(context: dict) -> str:
    """缓存包装：context 没变就返回缓存，避免重复拼接字符串。

    用 json.dumps 做确定性序列化，不用 Python 的 hash()——
    hash() 有进程随机化，且遇到 dict/list 会报 unhashable type。
    """
    global _last_context_key, _last_prompt
    key = json.dumps(context, sort_keys=True, ensure_ascii=False, default=str)
    if key == _last_context_key and _last_prompt:
        return _last_prompt
    _last_context_key = key
    _last_prompt = assemble_system_prompt(context)
    return _last_prompt
def update_context(context: dict, messages: list) -> dict:
    """从真实状态派生 context。"""
    from tools.builtin import BUILTIN_HANDLERS  # 延迟导入避免循环
    from services.skills import list_skills
    from tools.mcp import mcp_clients
    memories = ""
    if MEMORY_INDEX.exists():
        content = MEMORY_INDEX.read_text(encoding="utf-8").strip()
        if content:
            memories = content
    return {
        "enabled_tools": list(BUILTIN_HANDLERS.keys()),
        "workspace": str(WORKDIR),
        "memories": memories,
        "skills_catalog": list_skills(),
        "mcp_servers": list(mcp_clients.keys()),  # s19
    }
SUB_SYSTEM = (
    f"你是在 {WORKDIR} 工作的编程智能体。"
    "完成交给你的任务，然后返回简洁的总结。"
    "不要进一步委派。"
)
