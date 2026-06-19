"""子 Agent 系统 — s06"""
from config import safe_print,  client, PRIMARY_MODEL
from core.utils import extract_text, has_tool_use, call_tool_handler
from core.prompt import SUB_SYSTEM

def spawn_subagent(description: str) -> str:
    """s06: 派生子 Agent，全新上下文，只回传结论"""
    from tools.builtin import SUB_TOOLS, SUB_HANDLERS  # 延迟导入避免循环
    from runtime.hooks import trigger_hooks
    safe_print(f"\n\033[35m[子 Agent 已启动]\033[0m")
    messages = [{"role": "user", "content": description}]  # 全新的 messages[]

    for _ in range(30):  # 安全限制：最多 30 轮
        response = client.messages.create(
            model=PRIMARY_MODEL, system=SUB_SYSTEM,
            messages=messages, tools=SUB_TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                # 子 Agent 也走权限钩子 — 上下文隔离不代表权限跳过
                blocked = trigger_hooks("PreToolUse", block)
                if blocked:
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": str(blocked)})
                    continue
                handler = SUB_HANDLERS.get(block.name)
                output = handler(**block.input) if handler else f"未知工具: {block.name}"
                trigger_hooks("PostToolUse", block, output)
                safe_print(f"  \033[90m[子] {block.name}: {str(output)[:100]}\033[0m")
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": output})
        messages.append({"role": "user", "content": results})

    # 只回传最后的文本结论，中间过程全部丢弃
    result = extract_text(messages[-1]["content"])
    if not result:
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                result = extract_text(msg["content"])
                if result:
                    break
        if not result:
            result = "子 Agent 在 30 轮后停止，没有给出最终答案。"
    safe_print(f"\033[35m[子 Agent 完成]\033[0m")
    return result
