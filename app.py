#!/usr/bin/env python3
"""
s20 Comprehensive Agent — 入口
将所有模块组装在一起，启动交互式对话循环。
"""
import threading
from config import *
from core.utils import *
from core.prompt import *
from core.compression import *
from core.recovery import *
from core.engine import *
from services.skills import *
from services.memory import *
from services.tasks import *
from services.cron import *
from services.background import *
from tools.builtin import *
from tools.subagent import *
from tools.team import *
from tools.mcp import *
from runtime.hooks import *
from runtime.bus import *
from runtime.protocol import *
from runtime.teammate import *
from runtime.worktree import *

# 延迟初始化：在所有模块加载完成后，填充 handler 映射表
init_builtin_handlers()
init_sub_handlers()

if __name__ == "__main__":
    print("s20: Comprehensive Agent — 机制很多，循环一个")
    print("输入问题，回车发送。输入 q 退出。使用 schedule_cron 设置定时任务。\n")

    # s14+s20: 加载 durable 任务 + 启动 cron 调度 + 自动运行线程
    load_durable_jobs()
    threading.Thread(target=cron_scheduler_loop, daemon=True).start()
    print("  \033[35m[cron] 调度线程已启动\033[0m")

    session_history: list = []
    session_context = update_context({}, [])
    threading.Thread(target=cron_autorun_loop,
                     args=(session_history, session_context), daemon=True).start()
    print("  \033[35m[cron 自动运行] 已启动\033[0m")

    while True:
        try:
            query = input("\033[36ms20 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if not query.strip():  # 空输入重新提示
            continue
        if query.strip().lower() in ("q", "exit"):
            break
        trigger_hooks("UserPromptSubmit", query)
        turn_start = len(session_history)
        session_history.append({"role": "user", "content": query})
        with agent_lock:
            session_context = agent_loop(session_history, session_context)
        session_context = update_context(session_context, session_history)
        print_turn_assistants(session_history, turn_start)
        # s15: 检查 Lead 收件箱，队友消息注入 history
        inbox_msgs = consume_lead_inbox(route_protocol=True)
        if inbox_msgs:
            inbox_text = "\n".join(
                f"From {m['from']}: {m['content'][:200]}" for m in inbox_msgs)
            session_history.append({"role": "user",
                                    "content": f"[收件箱]\n{inbox_text}"})
            print(f"\n\033[33m[收件箱: {len(inbox_msgs)} 条消息]\033[0m")
        print()
