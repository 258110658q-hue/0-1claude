# mes1 项目拆分提示词（方案 B：大模块聚合）

请将 `mes1.py`（约 2745 行）拆分为 **6 个大文件**，按功能内聚合并。只做代码搬运和 import 调整，**不改任何业务逻辑、中文注释、ANSI 颜色代码**。

---

## 一、设计理念

- 文件数尽可能少，每个文件内部高度内聚
- 强耦合的功能塞到一起，不人为拆散
- 像一个人自己开发的项目，简单直接
- 根目录：`d:\Agent\0-1claude\`

---

## 二、目标文件结构

```
0-1claude/
├── app.py              # 主入口（~70行）
├── config.py           # 全局配置 + 通用工具函数（~250行）
├── engine.py           # 核心引擎（~550行）
├── tools.py            # 工具全集（~900行）
├── knowledge.py        # 知识 + 任务 + 调度（~550行）
└── collaboration.py    # 协作 + 隔离 + 协议（~550行）
```

---

## 三、每个文件的精确内容

### 3.1 `config.py` — 全局配置 + 通用工具（~250行）

把所有 import、配置、路径、通用小函数放一起，充当整个项目的"地基"。

```
搬运内容（按原 mes1.py 行号顺序）：

第一部分 — 头部和导入：
  # 1-49:     shebang + 顶部多行注释
  # 51-55:    import ast, json, os, subprocess, time, random, re, threading
               from pathlib import Path
               from datetime import datetime
               from dataclasses import dataclass, asdict, field
               import yaml
  # 59-68:    readline 兼容性修复 + READLINE_AVAILABLE
  # 70-71:    from anthropic import Anthropic; from dotenv import load_dotenv
  # 75-80:    .env 加载逻辑

第二部分 — 全局常量：
  # 82-92:    WORKDIR, SKILLS_DIR, TRANSCRIPT_DIR, TOOL_RESULTS_DIR,
               MEMORY_DIR, MEMORY_INDEX, TASKS_DIR, WORKTREES_DIR, VALID_WT_NAME
  # 93:       CURRENT_TODOS: list[dict] = []
  # 95:       client = Anthropic(...)
  # 97:       PRIMARY_MODEL = ...
  # 98:       FALLBACK_MODEL = ...

第三部分 — 通用工具函数（从原文件各处汇集）：
  # 102-116:  terminal_print(text)
  # 640-647:  safe_path(p, cwd=None)
  # 1035-1041: extract_text(content)
  # 1044-1047: has_tool_use(content)
  # 1050-1057: call_tool_handler(handler, args, name)
  # 1199-1201: estimate_size(msgs)
  # 1203-1205: _block_type(block)
  # 1207-1214: _message_has_tool_use(msg)
  # 1216-1224: _is_tool_result_message(msg)
```

顶层 import 就是 stdlib + anthropic + dotenv + yaml，不导入任何兄弟模块。

---

### 3.2 `engine.py` — 核心引擎（~550行）

把 agent_loop 主循环及其直接依赖的全部机制放在一起——压缩、恢复、prompt 拼装、上下文管理。

```
搬运内容（按原 mes1.py 行号顺序）：

第一部分 — System Prompt 系统：
  # 442-447:  PROMPT_SECTIONS 字典
  # 449-472:  assemble_system_prompt(context)
  # 475-476:  _last_context_key, _last_prompt
  # 479-491:  get_system_prompt(context)
  # 494-508:  update_context(context, messages)
  # 515-519:  SUB_SYSTEM 常量

第二部分 — 上下文压缩管线（s08）：
  # 1183-1186: CONTEXT_LIMIT, KEEP_RECENT, PERSIST_THRESHOLD, MAX_REACTIVE_RETRIES
  # 1227-1246: snip_compact(messages, max_messages=50)
  # 1249-1258: collect_tool_results(messages)
  # 1260-1268: micro_compact(messages)
  # 1271-1280: persist_large_output(tool_use_id, output)
  # 1282-1303: tool_result_budget(messages, max_bytes=200_000)
  # 1306-1313: write_transcript(messages)
  # 1315-1330: summarize_history(messages)
  # 1332-1337: compact_history(messages)
  # 1340-1349: reactive_compact(messages)

第三部分 — 错误恢复系统（s11）：
  # 1189-1197: ESCALATED_MAX_TOKENS, DEFAULT_MAX_TOKENS, MAX_RECOVERY_RETRIES,
               MAX_RETRIES, BASE_DELAY_MS, MAX_CONSECUTIVE_529, CONTINUATION_PROMPT
  # 1357-1364: RecoveryState 类
  # 1367-1376: retry_delay(attempt, retry_after=None)
  # 1379-1385: is_prompt_too_long_error(e)
  # 1388-1432: with_retry(fn, state)

第四部分 — agent_loop 核心循环 + 辅助函数（s20）：
  # 2487:     rounds_since_todo = 0
  # 2490-2498: prepare_context(messages)
  # 2501-2506: build_user_content(results)
  # 2509-2514: inject_background_notifications(messages)
  # 2517-2525: call_llm(messages, context, tools, state, max_tokens)
  # 2528-2535: print_turn_assistants(messages, turn_start)
  # 2538-2684: agent_loop(messages, context)
  # 2689-2704: cron_autorun_loop(history, context)
```

**顶部 import**：
```python
import json, time, threading
from config import (WORKDIR, TRANSCRIPT_DIR, TOOL_RESULTS_DIR, MEMORY_INDEX, CURRENT_TODOS,
                    client, PRIMARY_MODEL, FALLBACK_MODEL, READLINE_AVAILABLE,
                    terminal_print, extract_text, has_tool_use, call_tool_handler,
                    estimate_size, _block_type, _message_has_tool_use, _is_tool_result_message)

# 函数内部延迟导入（避免循环）：
#   from knowledge import (load_memories, extract_memories, consolidate_memories, read_memory_index,
#                          list_skills, consume_cron_queue, collect_background_results,
#                          should_run_background, start_background_task)
#   from tools import assemble_tool_pool, BUILTIN_HANDLERS
#   from collaboration import trigger_hooks, consume_lead_inbox
```

**关键延迟导入点**：
- `agent_loop()` 函数体第一行：`from knowledge import ...` 和 `from tools import ...` 和 `from collaboration import ...`
- `assemble_system_prompt()` 内：`from tools import mcp_clients`
- `update_context()` 内：`from tools import BUILTIN_HANDLERS` + `from knowledge import list_skills, read_memory_index` + `from tools import mcp_clients`

---

### 3.3 `tools.py` — 工具全集（~900行）

所有 LLM 可调用的工具——定义、handler、子 Agent、MCP，全部在这里。

```
搬运内容（按原 mes1.py 行号顺序）：

第一部分 — 基础工具执行函数：
  # 649-665:  run_bash(command, run_in_background=False, cwd=None)
  # 667-675:  run_read(path, limit=None, cwd=None)
  # 677-685:  run_write(path, content, cwd=None)
  # 687-696:  run_edit(path, old_text, new_text)
  # 698-707:  run_find(pattern)

第二部分 — 技能 + 任务 handler：
  # 999-1018: _normalize_todos(todos)
  # 1020-1032: run_todo_write(todos)
  # 1104-1109: load_skill(name)
  # 123-134:  _parse_frontmatter(text)        ← 从 skills 区搬来
  # 137-153:  SKILL_REGISTRY, _scan_skills()   ← 从 skills 区搬来
  # 156-160:  list_skills()                    ← 从 skills 区搬来

第三部分 — 子 Agent（s06）：
  # 1060-1101: spawn_subagent(description)

第四部分 — 任务 handler（s12 的 handler 部分 + Task 相关）：
  # 711-716:  run_create_task(subject, description="", blockedBy=None)
  # 719-732:  run_list_tasks()
  # 735-739:  run_get_task(task_id)
  # 742-743:  run_claim_task(task_id)
  # 746-747:  run_complete_task(task_id)

第五部分 — cron handler（s14 handler 部分）：
  # 752-757:  run_schedule_cron(cron, prompt, recurring=True, durable=True)
  # 760-770:  run_list_crons()
  # 773-774:  run_cancel_cron(job_id)

第六部分 — 团队 handler（s15+s16 handler 部分）：
  # 779-780:  run_spawn_teammate(name, role, prompt)
  # 783-785:  run_send_message(to, content)
  # 788-799:  run_check_inbox()
  # 804-814:  run_request_shutdown(teammate)
  # 817-819:  run_request_plan(teammate, task)
  # 823-837:  run_review_plan(request_id, approve, feedback="")

第七部分 — worktree + MCP handler（s18+s19 handler 部分）：
  # 842-844:  run_create_worktree(name, task_id="")
  # 847-849:  run_remove_worktree(name, discard_changes=False)
  # 852-854:  run_keep_worktree(name)
  # 857-859:  run_connect_mcp(name)

第八部分 — MCP 插件系统（s19 核心）：
  # 869-892:  MCPClient 类
  # 895-903:  mcp_clients 字典, _DISALLOWED_CHARS, normalize_mcp_name()
  # 910-927:  _mock_server_docs()
  # 930-949:  _mock_server_deploy()
  # 952-955:  MOCK_SERVERS
  # 958-972:  connect_mcp(name)
  # 975-995:  assemble_tool_pool()

第九部分 — 工具定义（放在文件最末尾）：
  # 523-636:  BUILTIN_TOOLS 列表
  # 1131-1167: SUB_TOOLS 列表
  # 1112-1128: BUILTIN_HANDLERS 字典
  # 1170-1176: SUB_HANDLERS 字典
```

**注意**：`BUILTIN_HANDLERS` 和 `SUB_HANDLERS` 字典中的值引用了本文件内的函数，放在文件尾部定义即可（Python 函数定义在前，字典引用在后，这是合法的——字典中的函数名在字典被求值时已存在）。

**顶部 import**：
```python
import json, subprocess, threading, re, glob as g
from config import (WORKDIR, SKILLS_DIR, TASKS_DIR, WORKTREES_DIR, CURRENT_TODOS,
                    safe_path, extract_text, has_tool_use, call_tool_handler)

# 延迟导入（函数内）：
#   from knowledge import (create_task, list_tasks, get_task, claim_task, complete_task,
#                          schedule_job, cancel_job, scheduled_jobs, cron_lock)
#   from collaboration import (BUS, pending_requests, new_request_id, ProtocolState,
#                              consume_lead_inbox, create_worktree, remove_worktree,
#                              keep_worktree, spawn_teammate_thread)
```

---

### 3.4 `knowledge.py` — 知识 + 任务 + 调度（~550行）

技能、记忆、任务图、cron 调度、后台任务——都是知识/状态管理类功能。

```
搬运内容（按原 mes1.py 行号顺序）：

第一部分 — 技能系统（s07，除 load_skill/handler 外）：
  # （_parse_frontmatter 和 SKILL_REGISTRY 和 _scan_skills 和 list_skills 已移到 tools.py）
  # （load_skill 已移到 tools.py）
  # 154:      _scan_skills()  ← skills 模块导入时自动执行，这里需保留调用

第二部分 — 记忆系统（s09，全部）：
  # 166-167:  MEMORY_TYPES, CONSOLIDATE_THRESHOLD
  # 169-181:  _parse_memory_frontmatter(text)
  # 183-193:  write_memory_file(name, mem_type, description, body)
  # 195-207:  _rebuild_index()
  # 209-214:  read_memory_index()
  # 216-221:  read_memory_file(filename)
  # 223-238:  list_memory_files()
  # 240-306:  select_relevant_memories(messages, max_items=5)
  # 308-320:  load_memories(messages)
  # 322-385:  extract_memories(messages)
  # 387-435:  consolidate_memories()

第三部分 — 任务系统核心（s12 + s17 scan_unclaimed）：
  # 1439-1447: Task dataclass
  # 1450-1451: _task_path(task_id)
  # 1454-1456: save_task(task)
  # 1459-1460: load_task(task_id)
  # 1463-1475: create_task(subject, description="", blockedBy=None)
  # 1478-1481: list_tasks()
  # 1484-1487: get_task(task_id)
  # 1490-1499: can_start(task_id)
  # 1503-1514: scan_unclaimed_tasks()
  # 1517-1534: claim_task(task_id, owner="agent")
  # 1537-1553: complete_task(task_id)

第四部分 — Cron 调度系统（s14，全部）：
  # 1757-1763: CronJob dataclass
  # 1766-1772: DURABLE_PATH, scheduled_jobs, cron_queue, cron_lock, agent_lock, _last_fired
  # 1775-1788: _cron_field_matches(field, value)
  # 1791-1816: cron_matches(cron_expr, dt)
  # 1819-1851: _validate_cron_field(field, lo, hi)
  # 1854-1865: validate_cron(cron_expr)
  # 1868-1873: save_durable_jobs()
  # 1876-1893: load_durable_jobs()
  # 1896-1912: schedule_job(cron, prompt, recurring=True, durable=True)
  # 1915-1924: cancel_job(job_id)
  # 1927-1948: cron_scheduler_loop()
  # 1951-1956: consume_cron_queue()
  # 1959-1962: has_cron_queue()

第五部分 — 后台任务系统（s13，全部）：
  # 1677-1680: _bg_counter, background_tasks, background_results, background_lock
  # 1683-1691: is_slow_operation(tool_name, tool_input)
  # 1694-1698: should_run_background(tool_name, tool_input)
  # 1701-1726: start_background_task(block, handlers)
  # 1729-1749: collect_background_results()
```

**顶部 import**：
```python
import json, time, threading, random, re
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from config import (WORKDIR, MEMORY_DIR, MEMORY_INDEX, TASKS_DIR, client, PRIMARY_MODEL,
                    extract_text, call_tool_handler)

# 延迟导入（函数内）：
#   start_background_task() 内: from collaboration import trigger_hooks
```

**注意**：
- `start_background_task` 调用了 `trigger_hooks("PostToolUse", ...)`，改为函数内 `from collaboration import trigger_hooks`
- `_scan_skills()` 原本在 mes1.py 用 `from config import SKILLS_DIR`，但 `SKILL_REGISTRY` 和 `_scan_skills` 函数体在 tools.py，调用在 knowledge.py。解决：`knowledge.py` 导入时调用 `tools._scan_skills()`（tools 的函数操作 tools.SKILL_REGISTRY，knowledge 只是触发者）

---

### 3.5 `collaboration.py` — 协作 + 隔离 + 协议（~550行）

钩子、MessageBus、协议、队友线程、worktree——全部是多 Agent 协作的运行时设施。

```
搬运内容（按原 mes1.py 行号顺序）：

第一部分 — 钩子系统（s04，全部）：
  # 2402-2414: HOOKS 字典, register_hook(), trigger_hooks()
  # 2418-2419: DENY_LIST, DESTRUCTIVE 常量
  # 2421-2449: permission_hook(block)
  # 2451-2455: log_hook(block)
  # 2457-2461: large_output_hook(block, output)
  # 2463-2466: context_inject_hook(query)
  # 2468-2474: summary_hook(messages)
  # 2476-2480: 5 个 register_hook() 调用（模块导入时自动执行）

第二部分 — MessageBus 消息总线（s15）：
  # 1971-1972: MAILBOX_DIR
  # 1975-1998: MessageBus 类
  # 2001-2002: BUS = MessageBus(), active_teammates

第三部分 — 协议系统（s16，全部）：
  # 2010-2018: ProtocolState dataclass
  # 2021:      pending_requests 字典
  # 2024-2025: new_request_id()
  # 2028-2051: match_response(response_type, request_id, approve)
  # 2054-2068: consume_lead_inbox(route_protocol=True)

第四部分 — Worktree 隔离系统（s18，全部）：
  # 1562-1571: validate_worktree_name(name)
  # 1574-1583: run_git(args)
  # 1586-1592: log_event(event_type, worktree_name, task_id="")
  # 1595-1611: create_worktree(name, task_id="")
  # 1614-1619: bind_task_to_worktree(task_id, worktree_name)
  # 1622-1633: _count_worktree_changes(path)
  # 1636-1660: remove_worktree(name, discard_changes=False)
  # 1663-1670: keep_worktree(name)

第五部分 — 队友自治 Agent（s17，全部）：
  # 2076-2077: IDLE_POLL_INTERVAL, IDLE_TIMEOUT
  # 2080-2137: idle_poll(agent_name, messages, name, role, worktree_context)
  # 2142-2397: spawn_teammate_thread(name, role, prompt)
```

**顶部 import**：
```python
import json, subprocess, time, threading, random, re
from pathlib import Path
from dataclasses import dataclass, asdict, field
from config import (WORKDIR, WORKTREES_DIR, VALID_WT_NAME, MAILBOX_DIR,
                    client, PRIMARY_MODEL, READLINE_AVAILABLE,
                    has_tool_use, call_tool_handler, terminal_print,
                    run_bash, run_read, run_write)

# 延迟导入（函数内）：
#   bind_task_to_worktree() 内: from knowledge import load_task, save_task
#   create_worktree() 内: from knowledge import bind_task_to_worktree (改名，或用 load_task/save_task)
#   spawn_teammate_thread() 内: from knowledge import list_tasks, claim_task, load_task, complete_task, scan_unclaimed_tasks
#   spawn_teammate_thread() 内: from tools import SUB_TOOLS, SUB_HANDLERS
```

**关键注意**：`MAILBOX_DIR` 原本在 mes1.py 的 s15 区定义，需要添加到 `config.py` 中：
```python
# 在 config.py 添加：
MAILBOX_DIR = WORKDIR / ".mailboxes"
MAILBOX_DIR.mkdir(exist_ok=True)
```

---

### 3.6 `app.py` — 主入口（~70行）

```python
#!/usr/bin/env python3
"""
s20 Comprehensive Agent — 入口。
将所有模块组装在一起，启动交互式对话循环。
"""
import threading
from config import *
from engine import *
from tools import *
from knowledge import *
from collaboration import *

# 导入时自动触发：技能扫描、钩子注册、durable job 加载

if __name__ == "__main__":
    print("s20: Comprehensive Agent — 机制很多，循环一个")
    print("输入问题，回车发送。输入 q 退出。使用 schedule_cron 设置定时任务。\n")

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

## 四、延迟导入总汇

方案 B 只有 5 个文件互引，循环依赖点很少。以下 6 处需要函数内延迟 import：

| 文件 | 函数 | 延迟导入 |
|------|------|---------|
| `engine.py` | `agent_loop()` | `knowledge`, `tools`, `collaboration` |
| `engine.py` | `assemble_system_prompt()` | `tools.mcp_clients` |
| `engine.py` | `update_context()` | `tools.BUILTIN_HANDLERS`, `knowledge.list_skills`, `knowledge.read_memory_index`, `tools.mcp_clients` |
| `tools.py` | 团队/worktree handler | `knowledge` (task 函数), `collaboration` (worktree/teammate 函数) |
| `knowledge.py` | `start_background_task()` | `collaboration.trigger_hooks` |
| `collaboration.py` | `spawn_teammate_thread()` | `knowledge` (task 函数) |

---

## 五、需要在 config.py 补充的内容

原 `mes1.py` 中 `MAILBOX_DIR` 定义在 s15 区（第 1971-1972 行），拆分后在 `collaboration.py` 用到。将以下两行加入 `config.py` 的全局常量区：

```python
MAILBOX_DIR = WORKDIR / ".mailboxes"
MAILBOX_DIR.mkdir(exist_ok=True)
```

---

## 六、需要在 knowledge.py 补充的 import 触发

原 `mes1.py` 第 154 行 `_scan_skills()` 在模块顶层执行。现在 `SKILL_REGISTRY` 和 `_scan_skills()` 在 `tools.py`。解决方法：

在 `tools.py` 末尾（`_scan_skills()` 定义之后）添加：
```python
# 模块导入时自动扫描技能目录
_scan_skills()
```

这样 `import tools` 时自动执行。

---

## 七、执行步骤

1. 创建 5 个新文件：`config.py` `engine.py` `tools.py` `knowledge.py` `collaboration.py` `app.py`
2. 按顺序搬运代码：config → engine → tools → knowledge → collaboration → app
3. 每搬运完一个文件，检查顶层 import 是否正确
4. 处理延迟导入（按第四章的表格）
5. 将原 `mes1.py` 重命名为 `mes1_backup.py`（备份）
6. 运行 `python app.py`，确保正常启动

---

## 八、验证清单

- [ ] `python app.py` 启动不报 ImportError
- [ ] 输入 "hello" 后 LLM 正常回复
- [ ] 技能目录扫描正常（启动时打印）
- [ ] cron 调度线程启动正常
- [ ] 钩子触发正常
- [ ] 所有 ANSI 颜色和中文注释保持原样
- [ ] 没有任何业务逻辑被改动
