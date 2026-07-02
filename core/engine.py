"""核心引擎 — agent_loop + cron_autorun_loop"""
import time
from config import safe_print,  WORKDIR, CURRENT_TODOS, client
from core.utils import has_tool_use, call_tool_handler, terminal_print, extract_text
from core.compression import tool_result_budget, snip_compact, micro_compact, compact_history, reactive_compact, CONTEXT_LIMIT, estimate_size
from core.recovery import RecoveryState, DEFAULT_MAX_TOKENS, ESCALATED_MAX_TOKENS, MAX_RECOVERY_RETRIES, CONTINUATION_PROMPT, with_retry, is_prompt_too_long_error
from core.prompt import assemble_system_prompt, update_context

rounds_since_todo = 0  # s05: 记录连续多少轮没有更新 todo
def prepare_context(messages: list) -> list:
    """LLM 调用前的上下文准备管线：L3→L1→L2→阈值?→L4"""
    messages[:] = tool_result_budget(messages)    # L3: 大结果落盘
    messages[:] = snip_compact(messages)          # L1: 裁剪中间消息
    messages[:] = micro_compact(messages)         # L2: 旧结果占位
    if estimate_size(messages) > CONTEXT_LIMIT:
        safe_print("[自动压缩]")
        messages[:] = compact_history(messages)   # L4: LLM 摘要
    return messages
def build_user_content(results: list[dict]) -> list[dict]:
    """合并工具结果和后台通知为用户消息内容。"""
    from services.background import collect_background_results  # 延迟导入
    content = list(results)
    for note in collect_background_results():
        content.append({"type": "text", "text": note})
    return content
def inject_background_notifications(messages: list):
    """将已完成的后台任务通知注入 messages。"""
    from services.background import collect_background_results  # 延迟导入
    notes = collect_background_results()
    if notes:
        messages.append({"role": "user", "content": [
            {"type": "text", "text": note} for note in notes]})

def inject_teammate_inbox(messages: list):
    """将队友发来的消息自动注入 messages（避免消息躺在收件箱无人查看）。"""
    from runtime.protocol import consume_lead_inbox  # 延迟导入
    msgs = consume_lead_inbox(route_protocol=True)
    if msgs:
        text = "<teammate_inbox>队友发来消息：\n"
        for m in msgs:
            text += f"  [{m['from']}] {str(m['content'])[:600]}\n"
        text += "</teammate_inbox>"
        messages.append({"role": "user", "content": text})

def call_llm(messages: list, context: dict, tools: list,
             state, max_tokens: int):
    """LLM 调用包装：组装 system prompt + with_retry 错误恢复。"""
    system = assemble_system_prompt(context)
    return with_retry(
        lambda: client.messages.create(
            model=state.current_model, system=system,
            messages=messages, tools=tools, max_tokens=max_tokens),
        state)
def print_turn_assistants(messages: list, turn_start: int):
    """打印本轮新产生的 assistant 文本回复。"""
    for msg in messages[turn_start:]:
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []):
            if getattr(block, "type", None) == "text":
                terminal_print(block.text)
def agent_loop(messages: list, context: dict):
    """智能体循环: 注入记忆 → 压缩 → 执行 → 提取记忆。"""
    global rounds_since_todo
    # s20: 延迟导入避免 core <-> services/tools/runtime 循环依赖
    from services.memory import load_memories, extract_memories, consolidate_memories
    from services.cron import consume_cron_queue
    from services.background import collect_background_results, should_run_background, start_background_task
    from tools.mcp import assemble_tool_pool
    from runtime.hooks import trigger_hooks
    tools, handlers = assemble_tool_pool()
    state = RecoveryState()
    max_tokens = DEFAULT_MAX_TOKENS

    # s09: 加载记忆（只做一次，内容不变）
    memories_content = load_memories(messages)

    while True:
        # s14: 注入已触发的 cron 任务
        fired = consume_cron_queue()
        for job in fired:
            messages.append({"role": "user",
                             "content": f"[定时任务] {job.prompt}"})

        # s13: 注入已完成的后台任务通知
        inject_background_notifications(messages)

        # s20: 自动注入队友消息（避免消息躺在收件箱无人查看）
        inject_teammate_inbox(messages)

        # s05: nag 提醒
        if rounds_since_todo >= 3 and messages:
            messages.append({"role": "user",
                             "content": "<reminder>请更新你的任务列表 (todo_write)。</reminder>"})
            rounds_since_todo = 0

        # s09: 保存压缩前快照
        pre_compress = [{k: v for k, v in m.items()} if isinstance(m, dict)
                        else {"role": getattr(m, "role", ""),
                              "content": str(getattr(m, "content", ""))}
                        for m in messages]

        # s20: 上下文准备管线
        prepare_context(messages)
        context = update_context(context, messages)
        tools, handlers = assemble_tool_pool()

        # s09: 记忆拼接到最新一条纯文本 user 消息前面
        #       每轮重算 memory_turn — prepare_context 可能重组消息列表
        request_messages = messages
        if memories_content:
            for i in range(len(messages) - 1, -1, -1):
                if (messages[i].get("role") == "user"
                        and isinstance(messages[i].get("content"), str)):
                    request_messages = messages.copy()
                    request_messages[i] = {
                        **messages[i],
                        "content": memories_content + "\n\n" + messages[i]["content"],
                    }
                    break

        # ── LLM 调用 + 错误恢复 ──
        try:
            response = call_llm(request_messages, context, tools, state, max_tokens)
        except Exception as e:
            if is_prompt_too_long_error(e) and not state.has_attempted_reactive_compact:
                messages[:] = reactive_compact(messages)
                state.has_attempted_reactive_compact = True
                continue
            name = type(e).__name__
            messages.append({"role": "assistant", "content": [
                {"type": "text", "text": f"[错误] {name}: {str(e)[:200]}"}]})
            return context

        # ── max_tokens 截断恢复 ──
        if response.stop_reason == "max_tokens":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                continue
            messages.append({"role": "assistant", "content": response.content})
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            return context

        # 正常完成
        messages.append({"role": "assistant", "content": response.content})

        # s20: 用 has_tool_use 替代 stop_reason
        if not has_tool_use(response.content):
            # s21: 空响应兜底 — DeepSeek 等弱模型在上下文混乱时可能返回空 content
            text = extract_text(response.content).strip()
            if not text:
                messages[-1] = {"role": "assistant", "content": [
                    {"type": "text", "text": "抱歉，模型暂时无法响应，请重试。"}
                ]}
                terminal_print("  \033[31m[错误] 模型返回空响应，请重试\033[0m")
                extract_memories(pre_compress)
                consolidate_memories()
                return context
            extract_memories(pre_compress)
            consolidate_memories()
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return context

        # ── 工具执行 ──
        results = []
        compacted_now = False
        for block in response.content:
            if block.type != "tool_use":
                continue
            safe_print(f"\033[36m> {block.name}\033[0m")

            # compact 特殊处理
            if block.name == "compact":
                messages[:] = compact_history(messages)
                messages.append({"role": "user",
                                 "content": "[已压缩。继续基于摘要工作。]"})
                compacted_now = True
                break

            # 权限钩子
            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": str(blocked)})
                continue

            # 后台任务分叉
            if should_run_background(block.name, block.input):
                bg_id = start_background_task(block, handlers)
                output = (f"[后台任务 {bg_id} 已启动] "
                          "完成后会以通知形式返回结果。")
                results.append({"type": "tool_result",
                                "tool_use_id": block.id, "content": output})
                continue

            # 同步执行
            handler = handlers.get(block.name)
            output = call_tool_handler(handler, block.input, block.name)
            trigger_hooks("PostToolUse", block, output)

            if block.name == "todo_write":
                rounds_since_todo = 0
            else:
                rounds_since_todo += 1

            results.append({"type": "tool_result",
                            "tool_use_id": block.id, "content": output})

        if compacted_now:
            continue

        messages.append({"role": "user", "content": build_user_content(results)})

        # s19: connect_mcp 后重建工具池
        if any(b.name == "connect_mcp" for b in response.content
               if b.type == "tool_use"):
            tools, handlers = assemble_tool_pool()


# ── s20: cron 自动运行 — 合并调度消费为一个线程 ──
# s14 用 cron_scheduler_loop + cron_queue + queue_processor_loop 三层解耦。
# s20 简化为单一 cron_autorun_loop：每秒检查一次，有触发就拉起 agent_loop。
def cron_autorun_loop(history: list, context: dict):
    """Cron 自动运行循环：每秒轮询 cron 队列，有触发则拉起 agent_loop 执行。"""
    from services.cron import consume_cron_queue, agent_lock  # 延迟导入
    from core.prompt import update_context
    import time
    while True:
        time.sleep(1)
        fired = consume_cron_queue()
        if not fired:
            continue
        with agent_lock:
            turn_start = len(history)
            for job in fired:
                history.append({"role": "user",
                                "content": f"[定时任务] {job.prompt}"})
                terminal_print(
                    f"  \033[35m[cron 自动] {job.prompt[:60]}\033[0m")
            agent_loop(history, context)
            context.update(update_context(context, history))
            print_turn_assistants(history, turn_start)
