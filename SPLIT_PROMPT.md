# mes1 项目拆分提示词

你是一个十年经验的 Python 架构师。请将 `mes1.py`（一个约 2745 行的单体 AI 编程智能体项目）拆分为多个功能独立的模块文件。

## 核心原则

1. **每个版本号（s01-s20）的功能独立成模块**，相关功能合并到一个文件
2. **主入口 `mes1.py` 只保留**：导入、`__main__` 入口、`agent_loop` 核心循环、`cron_autorun_loop`
3. **所有函数/类/常量保持原名**，不重命名
4. **import 关系清晰**：每个文件顶部明确列出从哪些兄弟模块导入什么
5. **根目录**：`d:\Agent\0-1claude\`，所有新文件直接放在这个目录下
6. **中文注释**保留原样不修改
7. **不要改变任何业务逻辑**，只做文件拆分和 import 调整

## 目标文件结构

```
d:\Agent\0-1claude\
├── mes1.py                 # 主入口（精简后约 200 行）
├── config.py               # 配置：导入、环境、路径常量、客户端
├── utils.py                # 通用工具函数
├── skills.py               # s07: 技能系统
├── memory.py               # s09: 记忆系统
├── prompt.py               # s10: System Prompt 分段组装
├── tools_definition.py     # 工具定义（BUILTIN_TOOLS, SUB_TOOLS）
├── tool_handlers.py        # 工具执行函数 + 映射表
├── hooks.py                # s04: 钩子系统
├── task_system.py          # s12+s17: 任务系统（Task dataclass + CRUD + handlers + scan_unclaimed）
├── compression.py          # s08: 四层上下文压缩管线
├── error_recovery.py       # s11: 错误恢复系统
├── sub_agent.py            # s06: 子 Agent 系统
├── background_tasks.py     # s13: 后台任务系统
├── cron_system.py          # s14: Cron 调度系统
├── message_bus.py          # s15: MessageBus 消息总线
├── protocol.py             # s16: 协议系统（请求-响应 + request_id 追踪）
├── worktree.py             # s18: Worktree 隔离系统
├── mcp.py                  # s19: MCP 插件系统
├── teammates.py            # s15+s16+s17: 队友自治 Agent 线程
└── agent_loop.py           # s20: agent_loop 核心循环 + 辅助函数 + cron_autorun_loop
```

## 每个文件的详细拆分说明

---

### 1. `config.py` — 全局配置（约 100 行）

**包含内容（从 mes1.py 提取）：**
- 文件头部的 shebang 和多行注释（第 1-49 行）
- 所有 import 语句（第 51-71 行）：`ast, json, os, subprocess, time, random, re, threading, pathlib, datetime, dataclasses, yaml, anthropic, dotenv`
- readline 兼容性修复（第 59-68 行）
- `READLINE_AVAILABLE` 常量
- `.env` 加载逻辑（第 74-80 行）
- 路径常量（第 82-92 行）：`WORKDIR, SKILLS_DIR, TRANSCRIPT_DIR, TOOL_RESULTS_DIR, MEMORY_DIR, MEMORY_INDEX, TASKS_DIR, WORKTREES_DIR, VALID_WT_NAME`
- `CURRENT_TODOS` 全局变量（第 93 行）
- `client` 实例化（第 95 行）
- `PRIMARY_MODEL` 和 `FALLBACK_MODEL`（第 97-98 行）

**被哪些文件导入**：几乎所有文件都需要 `WORKDIR`, `client`, `PRIMARY_MODEL` 等

---

### 2. `utils.py` — 通用工具函数（约 60 行）

**包含内容：**
- `terminal_print()` 函数（第 102-116 行）
- `extract_text()` 函数（第 1035-1041 行）
- `safe_path()` 函数（第 640-647 行）
- `has_tool_use()` 函数（第 1044-1047 行）
- `call_tool_handler()` 函数（第 1050-1057 行）
- `_block_type()` 函数（第 1203-1205 行）
- `_message_has_tool_use()` 函数（第 1207-1214 行）
- `_is_tool_result_message()` 函数（第 1216-1224 行）
- `estimate_size()` 函数（第 1199-1201 行）

**被哪些文件导入**：几乎所有文件

---

### 3. `skills.py` — s07 技能系统（约 60 行）

**包含内容：**
- `_parse_frontmatter()` 函数（第 123-134 行）
- `SKILL_REGISTRY` 全局字典（第 137 行）
- `_scan_skills()` 函数（第 139-153 行）
- `list_skills()` 函数（第 156-160 行）
- `load_skill()` 函数（第 1104-1109 行）
- 启动时的 `_scan_skills()` 调用（第 154 行）→ 改为在模块导入时自动执行

**依赖**：`config.py`（SKILLS_DIR, yaml）, `utils.py`

---

### 4. `memory.py` — s09 记忆系统（约 280 行）

**包含内容：**
- `MEMORY_TYPES`, `CONSOLIDATE_THRESHOLD` 常量（第 166-167 行）
- `_parse_memory_frontmatter()` 函数（第 169-181 行）
- `write_memory_file()` 函数（第 183-193 行）
- `_rebuild_index()` 函数（第 195-207 行）
- `read_memory_index()` 函数（第 209-214 行）
- `read_memory_file()` 函数（第 216-221 行）
- `list_memory_files()` 函数（第 223-238 行）
- `select_relevant_memories()` 函数（第 240-306 行）
- `load_memories()` 函数（第 308-320 行）
- `extract_memories()` 函数（第 322-385 行）
- `consolidate_memories()` 函数（第 387-435 行）

**依赖**：`config.py`（MEMORY_DIR, MEMORY_INDEX, client, PRIMARY_MODEL）, `utils.py`

---

### 5. `prompt.py` — s10 System Prompt 组装（约 70 行）

**包含内容：**
- `PROMPT_SECTIONS` 字典（第 442-447 行）
- `assemble_system_prompt()` 函数（第 449-472 行）
- `SUB_SYSTEM` 常量（第 515-519 行）
- `_last_context_key`, `_last_prompt` 全局变量（第 475-476 行）
- `get_system_prompt()` 函数（第 479-491 行）
- `update_context()` 函数（第 494-508 行）

**依赖**：`config.py`（WORKDIR）, `skills.py`（list_skills）, `memory.py`（read_memory_index）, `mcp.py`（mcp_clients）, `tools_definition.py`（BUILTIN_HANDLERS）

---

### 6. `tools_definition.py` — 工具定义（约 120 行）

**包含内容：**
- `BUILTIN_TOOLS` 列表（第 523-636 行）
- `SUB_TOOLS` 列表（第 1131-1167 行）

**依赖**：无外部依赖（纯数据定义）

---

### 7. `tool_handlers.py` — 工具执行函数 + 映射表（约 200 行）

**包含内容：**
- `run_bash()` 函数（第 649-665 行）
- `run_read()` 函数（第 667-675 行）
- `run_write()` 函数（第 677-685 行）
- `run_edit()` 函数（第 687-696 行）
- `run_find()` 函数（第 698-707 行）
- `_normalize_todos()` 函数（第 999-1018 行）
- `run_todo_write()` 函数（第 1020-1032 行）
- `BUILTIN_HANDLERS` 字典（第 1112-1128 行）
- `SUB_HANDLERS` 字典（第 1170-1176 行）

**注意**：`BUILTIN_HANDLERS` 的值引用了来自其他模块的函数（如 `run_create_task`, `run_schedule_cron`, `spawn_subagent` 等），需要在文件顶部 import 这些函数。

**依赖**：`config.py`, `utils.py`, `task_system.py`, `cron_system.py`, `teammates.py`, `protocol.py`, `worktree.py`, `mcp.py`, `sub_agent.py`, `skills.py`

---

### 8. `hooks.py` — s04 钩子系统（约 80 行）

**包含内容：**
- `HOOKS` 字典（第 2402 行）
- `register_hook()` 函数（第 2404-2406 行）
- `trigger_hooks()` 函数（第 2408-2414 行）
- `DENY_LIST`, `DESTRUCTIVE` 常量（第 2418-2419 行）
- `permission_hook()` 函数（第 2421-2449 行）
- `log_hook()` 函数（第 2451-2455 行）
- `large_output_hook()` 函数（第 2457-2461 行）
- `context_inject_hook()` 函数（第 2463-2466 行）
- `summary_hook()` 函数（第 2468-2474 行）
- 5 个 `register_hook()` 调用（第 2476-2480 行）→ 模块导入时自动执行

**依赖**：`config.py`（WORKDIR）

---

### 9. `task_system.py` — s12+s17 任务系统（约 160 行）

**包含内容：**
- `Task` dataclass 定义（第 1439-1447 行）
- `_task_path()` 函数（第 1450-1451 行）
- `save_task()` 函数（第 1454-1456 行）
- `load_task()` 函数（第 1459-1460 行）
- `create_task()` 函数（第 1463-1475 行）
- `list_tasks()` 函数（第 1478-1481 行）
- `get_task()` 函数（第 1484-1487 行）
- `can_start()` 函数（第 1490-1499 行）
- `scan_unclaimed_tasks()` 函数（第 1503-1514 行）
- `claim_task()` 函数（第 1517-1534 行）
- `complete_task()` 函数（第 1537-1553 行）
- `run_create_task()` 函数（第 711-716 行）
- `run_list_tasks()` 函数（第 719-732 行）
- `run_get_task()` 函数（第 735-739 行）
- `run_claim_task()` 函数（第 742-743 行）
- `run_complete_task()` 函数（第 746-747 行）

**依赖**：`config.py`（TASKS_DIR, random, time）, `utils.py`

---

### 10. `compression.py` — s08 上下文压缩管线（约 170 行）

**包含内容：**
- 压缩常量（第 1183-1186 行）：`CONTEXT_LIMIT, KEEP_RECENT, PERSIST_THRESHOLD, MAX_REACTIVE_RETRIES`
- `snip_compact()` 函数（第 1227-1246 行）
- `micro_compact()` 函数 / `collect_tool_results()` 函数（第 1249-1268 行）
- `persist_large_output()` 函数（第 1271-1280 行）
- `tool_result_budget()` 函数（第 1282-1303 行）
- `write_transcript()` 函数（第 1306-1313 行）
- `summarize_history()` 函数（第 1315-1330 行）
- `compact_history()` 函数（第 1332-1337 行）
- `reactive_compact()` 函数（第 1340-1349 行）

**依赖**：`config.py`（TRANSCRIPT_DIR, TOOL_RESULTS_DIR, client, PRIMARY_MODEL）, `utils.py`

---

### 11. `error_recovery.py` — s11 错误恢复系统（约 100 行）

**包含内容：**
- 错误恢复常量（第 1189-1197 行）：`ESCALATED_MAX_TOKENS, DEFAULT_MAX_TOKENS, MAX_RECOVERY_RETRIES, MAX_RETRIES, BASE_DELAY_MS, MAX_CONSECUTIVE_529, CONTINUATION_PROMPT`
- `RecoveryState` 类（第 1357-1364 行）
- `retry_delay()` 函数（第 1367-1376 行）
- `is_prompt_too_long_error()` 函数（第 1379-1385 行）
- `with_retry()` 函数（第 1388-1432 行）

**依赖**：`config.py`（PRIMARY_MODEL, FALLBACK_MODEL, time, random）

---

### 12. `sub_agent.py` — s06 子 Agent 系统（约 70 行）

**包含内容：**
- `spawn_subagent()` 函数（第 1060-1101 行）

**依赖**：`config.py`（client, PRIMARY_MODEL）, `prompt.py`（SUB_SYSTEM）, `tools_definition.py`（SUB_TOOLS）, `tool_handlers.py`（SUB_HANDLERS）, `hooks.py`（trigger_hooks）, `utils.py`（extract_text）

---

### 13. `background_tasks.py` — s13 后台任务系统（约 80 行）

**包含内容：**
- `_bg_counter` 全局变量（第 1677 行）
- `background_tasks` 字典（第 1678 行）
- `background_results` 字典（第 1679 行）
- `background_lock` 锁（第 1680 行）
- `is_slow_operation()` 函数（第 1683-1691 行）
- `should_run_background()` 函数（第 1694-1698 行）
- `start_background_task()` 函数（第 1701-1726 行）
- `collect_background_results()` 函数（第 1729-1749 行）

**依赖**：`config.py`（threading）, `hooks.py`（trigger_hooks）, `utils.py`（call_tool_handler）

---

### 14. `cron_system.py` — s14 Cron 调度系统（约 210 行）

**包含内容：**
- `CronJob` dataclass（第 1757-1763 行）
- `DURABLE_PATH` 常量（第 1766 行）
- `scheduled_jobs` 字典（第 1768 行）
- `cron_queue` 列表（第 1769 行）
- `cron_lock` 锁（第 1770 行）
- `agent_lock` 锁（第 1771 行）
- `_last_fired` 字典（第 1772 行）
- `_cron_field_matches()` 函数（第 1775-1788 行）
- `cron_matches()` 函数（第 1791-1816 行）
- `_validate_cron_field()` 函数（第 1819-1851 行）
- `validate_cron()` 函数（第 1854-1865 行）
- `save_durable_jobs()` 函数（第 1868-1873 行）
- `load_durable_jobs()` 函数（第 1876-1893 行）
- `schedule_job()` 函数（第 1896-1912 行）
- `cancel_job()` 函数（第 1915-1924 行）
- `cron_scheduler_loop()` 函数（第 1927-1948 行）
- `consume_cron_queue()` 函数（第 1951-1956 行）
- `has_cron_queue()` 函数（第 1959-1962 行）
- `run_schedule_cron()` 函数（第 752-757 行）
- `run_list_crons()` 函数（第 760-770 行）
- `run_cancel_cron()` 函数（第 773-774 行）

**依赖**：`config.py`（WORKDIR, time, threading, random, datetime）

---

### 15. `message_bus.py` — s15 MessageBus 消息总线（约 35 行）

**包含内容：**
- `MAILBOX_DIR` 常量（第 1971-1972 行）
- `MessageBus` 类（第 1975-1998 行）
- `BUS` 实例（第 2001 行）
- `active_teammates` 字典（第 2002 行）

**依赖**：`config.py`（WORKDIR）

---

### 16. `protocol.py` — s16 协议系统（约 70 行）

**包含内容：**
- `ProtocolState` dataclass（第 2010-2018 行）
- `pending_requests` 字典（第 2021 行）
- `new_request_id()` 函数（第 2024-2025 行）
- `match_response()` 函数（第 2028-2051 行）
- `consume_lead_inbox()` 函数（第 2054-2068 行）
- `run_request_shutdown()` 函数（第 804-814 行）
- `run_request_plan()` 函数（第 817-819 行）
- `run_review_plan()` 函数（第 823-837 行）
- `run_check_inbox()` 函数（第 788-799 行）
- `run_spawn_teammate()` 函数（第 779-780 行）
- `run_send_message()` 函数（第 783-785 行）

**依赖**：`config.py`（random）, `message_bus.py`（BUS）, `teammates.py`（spawn_teammate_thread）

**⚠️ 循环依赖注意**：`protocol.py` 需要从 `teammates.py` 导入 `spawn_teammate_thread`，而 `teammates.py` 需要从 `protocol.py` 导入 `ProtocolState, pending_requests, new_request_id`。解决方法：
- `protocol.py` 中的 `run_spawn_teammate` 在函数内部延迟导入：`from teammates import spawn_teammate_thread`
- 或者将 `run_spawn_teammate`, `run_send_message`, `run_check_inbox` 移到 `teammates.py`

---

### 17. `worktree.py` — s18 Worktree 隔离系统（约 120 行）

**包含内容：**
- `validate_worktree_name()` 函数（第 1562-1571 行）
- `run_git()` 函数（第 1574-1583 行）
- `log_event()` 函数（第 1586-1592 行）
- `create_worktree()` 函数（第 1595-1611 行）
- `bind_task_to_worktree()` 函数（第 1614-1619 行）
- `_count_worktree_changes()` 函数（第 1622-1633 行）
- `remove_worktree()` 函数（第 1636-1660 行）
- `keep_worktree()` 函数（第 1663-1670 行）
- `run_create_worktree()` 函数（第 842-844 行）
- `run_remove_worktree()` 函数（第 847-849 行）
- `run_keep_worktree()` 函数（第 852-854 行）

**依赖**：`config.py`（WORKDIR, WORKTREES_DIR, VALID_WT_NAME）, `task_system.py`（load_task, bind_task_to_worktree 需要 save_task）

---

### 18. `mcp.py` — s19 MCP 插件系统（约 130 行）

**包含内容：**
- `MCPClient` 类（第 869-892 行）
- `mcp_clients` 字典（第 895 行）
- `_DISALLOWED_CHARS` 正则（第 897 行）
- `normalize_mcp_name()` 函数（第 900-903 行）
- `_mock_server_docs()` 函数（第 910-927 行）
- `_mock_server_deploy()` 函数（第 930-949 行）
- `MOCK_SERVERS` 字典（第 952-955 行）
- `connect_mcp()` 函数（第 958-972 行）
- `assemble_tool_pool()` 函数（第 975-995 行）
- `run_connect_mcp()` 函数（第 857-859 行）

**依赖**：`config.py`（re）, `tools_definition.py`（BUILTIN_TOOLS）, `tool_handlers.py`（BUILTIN_HANDLERS）

---

### 19. `teammates.py` — s15+s16+s17 队友自治 Agent（约 260 行）

**包含内容：**
- `IDLE_POLL_INTERVAL`, `IDLE_TIMEOUT` 常量（第 2076-2077 行）
- `idle_poll()` 函数（第 2080-2137 行）
- `spawn_teammate_thread()` 函数（第 2142-2397 行）

**依赖**：`config.py`（client, PRIMARY_MODEL, WORKDIR, WORKTREES_DIR, threading）, `message_bus.py`（BUS, active_teammates）, `protocol.py`（ProtocolState, pending_requests, new_request_id）, `task_system.py`（scan_unclaimed_tasks, claim_task, load_task, complete_task, list_tasks）, `worktree.py`（...）, `utils.py`（call_tool_handler, has_tool_use）, `compression.py`（...）

**⚠️ 循环依赖**：`spawn_teammate_thread` 需要从 `task_system.py` 导入，而 `task_system.py` 的 `run_claim_task` 在函数内部调用即可。`protocol.py` 需要 `spawn_teammate_thread`，使用延迟导入。

---

### 20. `agent_loop.py` — s20 agent_loop 核心 + 辅助函数 + cron_autorun_loop（约 150 行）

**包含内容：**
- `rounds_since_todo` 全局变量（第 2487 行）
- `prepare_context()` 函数（第 2490-2498 行）
- `build_user_content()` 函数（第 2501-2506 行）
- `inject_background_notifications()` 函数（第 2509-2514 行）
- `call_llm()` 函数（第 2517-2525 行）
- `print_turn_assistants()` 函数（第 2528-2535 行）
- `agent_loop()` 函数（第 2538-2684 行）
- `cron_autorun_loop()` 函数（第 2689-2704 行）

**依赖**：几乎所有模块

---

### 21. `mes1.py` — 主入口（精简后约 60 行）

**最终内容：**
```python
#!/usr/bin/env python3
"""s20: Comprehensive Agent — 入口"""

# 导入所有模块（它们会自动初始化技能、钩子、durable jobs）
from config import *
from utils import *
from skills import *
from memory import *
from prompt import *
from tools_definition import *
from tool_handlers import *
from hooks import *
from task_system import *
from compression import *
from error_recovery import *
from sub_agent import *
from background_tasks import *
from cron_system import *
from message_bus import *
from protocol import *
from worktree import *
from mcp import *
from teammates import *
from agent_loop import *

if __name__ == "__main__":
    print("s20: Comprehensive Agent — 机制很多，循环一个")
    print("输入问题，回车发送。输入 q 退出。使用 schedule_cron 设置定时任务。\n")

    # 加载 durable 任务 + 启动 cron 调度线程
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
        if query.strip().lower() in ("q", "exit", ""):
            break
        trigger_hooks("UserPromptSubmit", query)
        turn_start = len(session_history)
        session_history.append({"role": "user", "content": query})
        with agent_lock:
            session_context = agent_loop(session_history, session_context)
        session_context = update_context(session_context, session_history)
        print_turn_assistants(session_history, turn_start)
        # 检查收件箱
        inbox_msgs = consume_lead_inbox(route_protocol=True)
        if inbox_msgs:
            inbox_text = "\n".join(
                f"From {m['from']}: {m['content'][:200]}" for m in inbox_msgs)
            session_history.append({"role": "user",
                                    "content": f"[收件箱]\n{inbox_text}"})
            print(f"\n\033[33m[收件箱: {len(inbox_msgs)} 条消息]\033[0m")
        print()
```

---

## 循环依赖解决方案

以下模块对存在循环引用，统一用**延迟导入（lazy import）**处理：

| 模块 A | 需要从 B 导入 | 模块 B | 需要从 A 导入 | 解决方案 |
|--------|--------------|--------|--------------|----------|
| `protocol.py` | `spawn_teammate_thread` | `teammates.py` | `ProtocolState, pending_requests, new_request_id` | `protocol.py` 的函数内部 `from teammates import spawn_teammate_thread` |
| `prompt.py` | `BUILTIN_HANDLERS` | `tool_handlers.py` | 各种 handler 函数 | `prompt.py` 内部延迟导入 `from tool_handlers import BUILTIN_HANDLERS` |
| `tool_handlers.py` | `run_create_task` 等 | `task_system.py` | `Task, create_task` 等 | `tool_handlers.py` 的函数内部延迟导入 |

**延迟导入模板**：
```python
def run_create_task(subject, description="", blockedBy=None):
    from task_system import create_task  # 延迟导入避免循环
    task = create_task(subject, description, blockedBy)
    ...
```

---

## 执行步骤

请按以下顺序执行：

1. **创建所有新文件**（config.py → utils.py → skills.py → memory.py → ... → agent_loop.py → mes1.py）
2. **每个文件**：从 `mes1.py` 中精确复制对应的代码段
3. **添加文件顶部的 docstring 和 import 语句**
4. **处理循环依赖**：将跨模块调用的顶层 import 改为函数内部延迟导入
5. **将原 `mes1.py` 重命名为 `mes1_backup.py`**（保留备份）
6. **验证**：运行 `python mes1.py`，确保能正常启动

## 关键注意事项

1. **全局变量的单例性**：`BUS`, `client`, `SKILL_REGISTRY`, `mcp_clients`, `scheduled_jobs`, `cron_queue`, `background_tasks` 等全局对象必须在导入时就存在，且整个进程只有一份。利用 Python 的模块单例机制（每个模块只执行一次）自动保证。
2. **模块初始化副作用**：`hooks.py` 导入时自动执行 `register_hook()`，`skills.py` 导入时自动执行 `_scan_skills()`。这些副作用必须保留。
3. **threading.Event / Lock 等**：`cron_lock`, `agent_lock`, `background_lock` 等锁对象在原文件中是模块级全局变量，拆分后仍在各自模块中保持模块级全局。
4. **不要改动任何函数的内部实现**，只移动代码 + 调整 import。
5. **不要改动中文注释和 ANSI 颜色代码**。
