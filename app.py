#!/usr/bin/env python3
"""
s20 Comprehensive Agent — 入口
将所有模块组装在一起，启动交互式对话循环。
"""
import sys, os, threading
from pathlib import Path
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


def startup_check():
    """启动前自检，失败时给出明确的修复提示。"""
    errors = []

    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        errors.append(
            "未找到 .env 文件\n"
            "  解决: cp .env.example .env\n"
            "  然后编辑 .env 填入你的 API Key 和 MODEL_ID"
        )
    else:
        if not os.getenv("ANTHROPIC_API_KEY"):
            errors.append(
                "ANTHROPIC_API_KEY 未设置\n"
                "  解决: 编辑 .env 文件，设置 ANTHROPIC_API_KEY=你的密钥"
            )
        if not os.getenv("MODEL_ID"):
            errors.append(
                "MODEL_ID 未设置\n"
                "  解决: 编辑 .env 文件，设置 MODEL_ID=claude-sonnet-4-6"
            )

    if errors:
        print("\n[自检失败] 以下问题需要修复:\n")
        for i, e in enumerate(errors, 1):
            print(f"  {i}. {e}\n")
        return False

    print("[自检通过] .env 配置正确")
    return True


if __name__ == "__main__":
    # ── 命令行模式 ──

    if "--check" in sys.argv:
        ok = startup_check()
        if ok:
            print(f"  WORKDIR: {WORKDIR}")
            print(f"  MODEL_ID: {os.getenv('MODEL_ID')}")
            print(f"  技能数: {len(SKILL_REGISTRY)}")
            from tools.builtin import BUILTIN_HANDLERS
            print(f"  内置工具: {len(BUILTIN_HANDLERS)}")
            print(f"  测试命令: python -m pytest tests/ -v")
        sys.exit(0 if ok else 1)

    if "--test" in sys.argv:
        import pytest
        sys.exit(pytest.main(["tests/", "-v"]))

    # ── 正常启动 ──

    if not startup_check():
        sys.exit(1)

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
