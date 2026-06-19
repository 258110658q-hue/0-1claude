"""上下文压缩管线 — s08"""
import json, time
from config import safe_print,  TRANSCRIPT_DIR, TOOL_RESULTS_DIR, client, PRIMARY_MODEL
from core.utils import estimate_size, _block_type, _message_has_tool_use, _is_tool_result_message, extract_text

CONTEXT_LIMIT = 50000        # 字符数阈值，超过则触发 L4 自动摘要
KEEP_RECENT = 3              # L2 micro: 保留最近 N 条 tool_result 的完整内容
PERSIST_THRESHOLD = 30000    # L3 budget: 单条结果超过此大小就落盘
MAX_REACTIVE_RETRIES = 1     # 应急压缩最多重试次数
def snip_compact(messages, max_messages=50):
    """消息数超过上限时，保留头部和尾部，裁掉中间。0 API 调用。"""
    if len(messages) <= max_messages:
        return messages
    keep_head, keep_tail = 3, max_messages - 3
    head_end, tail_start = keep_head, len(messages) - keep_tail
    # 边界保护：不能把 assistant(tool_use) 和后面的 user(tool_result) 拆开
    if head_end > 0 and _message_has_tool_use(messages[head_end - 1]):
        while head_end < len(messages) and _is_tool_result_message(messages[head_end]):
            head_end += 1
    if (tail_start > 0 and tail_start < len(messages)
            and _is_tool_result_message(messages[tail_start])
            and _message_has_tool_use(messages[tail_start - 1])):
        tail_start -= 1
    if head_end >= tail_start:
        return messages
    snipped = tail_start - head_end
    return (messages[:head_end] +
            [{"role": "user", "content": f"[已裁剪中间 {snipped} 条消息]"}]
            + messages[tail_start:])
def collect_tool_results(messages):
    """收集所有 tool_result 块的位置信息。"""
    blocks = []
    for mi, msg in enumerate(messages):
        if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
            continue
        for bi, block in enumerate(msg["content"]):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                blocks.append((mi, bi, block))
    return blocks
def micro_compact(messages):
    """只保留最近 N 条 tool_result 的完整内容，更旧的替换为占位符。0 API 调用。"""
    tool_results = collect_tool_results(messages)
    if len(tool_results) <= KEEP_RECENT:
        return messages
    for _, _, block in tool_results[:-KEEP_RECENT]:
        if len(block.get("content", "")) > 120:
            block["content"] = "[早期工具结果已压缩。如需可重新执行。]"
    return messages
def persist_large_output(tool_use_id, output):
    """将超大工具输出写入磁盘，上下文里只留预览。"""
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOOL_RESULTS_DIR / f"{tool_use_id}.txt"
    if not path.exists():
        path.write_text(output, encoding="utf-8")
    return (f"<持久化输出>\n"
            f"完整输出: {path}\n"
            f"预览:\n{output[:2000]}\n"
            f"</持久化输出>")
def tool_result_budget(messages, max_bytes=200_000):
    """最后一条 user 消息中 tool_result 总大小超预算时，最大的先落盘。0 API 调用。"""
    last = messages[-1] if messages else None
    if not last or last.get("role") != "user" or not isinstance(last.get("content"), list):
        return messages
    blocks = [(i, b) for i, b in enumerate(last["content"])
              if isinstance(b, dict) and b.get("type") == "tool_result"]
    total = sum(len(str(b.get("content", ""))) for _, b in blocks)
    if total <= max_bytes:
        return messages
    # 按大小从大到小排序，最大的先落盘
    ranked = sorted(blocks, key=lambda p: len(str(p[1].get("content", ""))), reverse=True)
    for _, block in ranked:
        if total <= max_bytes:
            break
        content = str(block.get("content", ""))
        if len(content) <= PERSIST_THRESHOLD:
            continue
        tid = block.get("tool_use_id", "unknown")
        block["content"] = persist_large_output(tid, content)
        total = sum(len(str(b.get("content", ""))) for _, b in blocks)
    return messages
def write_transcript(messages):
    """将完整对话写入 .transcripts/ 作为存档。"""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with path.open("w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    return path
def summarize_history(messages):
    """调用 LLM 生成对话摘要（1 API 调用）。"""
    conversation = json.dumps(messages, default=str)[:80000]
    prompt = ("总结以下编程智能体会话，以便工作可以继续。\n"
              "保留：1. 当前目标 2. 关键发现/决策 3. 已读取/修改的文件 "
              "4. 剩余工作 5. 用户约束。\n"
              "简洁但具体。\n\n" + conversation)
    response = client.messages.create(
        model=PRIMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    return "\n".join(
        getattr(b, "text", "")
        for b in response.content
        if getattr(b, "type", None) == "text").strip() or "（空摘要）"
def compact_history(messages):
    """L4: 保存抄本 → LLM 摘要 → 替换消息列表（1 API 调用）。"""
    transcript_path = write_transcript(messages)
    safe_print(f"[对话抄本已保存: {transcript_path}]")
    summary = summarize_history(messages)
    return [{"role": "user", "content": f"[已压缩]\n\n{summary}"}]
def reactive_compact(messages):
    """API 仍报 prompt_too_long 时触发，比 compact_history 更激进。"""
    write_transcript(messages)  # 先存档完整对话
    summary = summarize_history(messages)
    tail_start = max(0, len(messages) - 5)
    if (tail_start > 0 and tail_start < len(messages)
            and _is_tool_result_message(messages[tail_start])
            and _message_has_tool_use(messages[tail_start - 1])):
        tail_start -= 1
    return [{"role": "user", "content": f"[应急压缩]\n\n{summary}"}, *messages[tail_start:]]
