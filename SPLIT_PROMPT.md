# mes1 项目拆分提示词（方案 A：领域分层）

请将 `mes1.py`（约 2745 行）按**领域分层架构**拆分为多个模块。只做代码搬运和 import 调整，**不改任何业务逻辑、中文注释、ANSI 颜色代码**。

---

## 一、架构理念

```
依赖方向（单向，不可逆）：
  core ──→ services ──→ tools ──→ runtime
           │                        │
           └────────────────────────┘
          services 也可以被 runtime 调用
```

- **core/** — 核心引擎，最稳定，不常改
- **services/** — 功能服务，被 engine 调用，对外不可见
- **tools/** — LLM 可调用的全部工具
- **runtime/** — 运行时设施（钩子、通信、队友、隔离）
- **根目录** — `d:\Agent\0-1claude\`，所有新文件夹创建在此

---

## 二、最终文件结构

```
0-1claude/
├── app.py                      # 主入口
├── config.py                   # 全局配置
├── core/
│   ├── __init__.py             # 空
│   ├── utils.py                # 通用工具函数
│   ├── prompt.py               # System Prompt 组装
│   ├── compression.py          # s08 上下文压缩
│   ├── recovery.py             # s11 错误恢复
│   └── engine.py               # agent_loop + cron_autorun_loop
├── services/
│   ├── __init__.py             # 空
│   ├── skills.py               # s07 技能系统
│   ├── memory.py               # s09 记忆系统
│   ├── tasks.py                # s12 任务图 + s17 扫描认领
│   ├── cron.py                 # s14 cron 调度
│   └── background.py           # s13 后台任务
├── tools/
│   ├── __init__.py             # 空
│   ├── builtin.py              # 工具定义 + 基础 handler
│   ├── subagent.py             # s06 子 Agent
│   ├── team.py                 # 团队/worktree/MCP 工具 handler
│   └── mcp.py                  # s19 MCP 插件系统
└── runtime/
    ├── __init__.py             # 空
    ├── hooks.py                # s04 钩子系统
    ├── bus.py                  # s15 MessageBus
    ├── protocol.py             # s16 协议系统
    ├── teammate.py             # s17 队友自治循环
    └── worktree.py             # s18 worktree 隔离
```

---

## 三、每个文件的精确内容

### 3.1 `config.py` — 全局配置

从 `mes1.py` 搬运以下内容，保持原样：

```
搬运内容（按行号）：
  # 1-49:     shebang + 顶部多行注释（整个模块的说明）
  # 51:       import ast, json, os, subprocess, time, random, re, threading
  # 52-55:    from pathlib import Path; from datetime import datetime; from dataclasses import ...; import yaml
  # 59-68:    readline 兼容性修复 + READLINE_AVAILABLE
  # 70-71:    from anthropic import Anthropic; from dotenv import load_dotenv
  # 75-80:    .env 加载逻辑
  # 82-92:    WORKDIR, SKILLS_DIR, TRANSCRIPT_DIR, TOOL_RESULTS_DIR, MEMORY_DIR, MEMORY_INDEX, TASKS_DIR, WORKTREES_DIR, VALID_WT_NAME
  # 93:       CURRENT_TODOS: list[dict] = []
  # 95:       client = Anthropic(...)
  # 97:       PRIMARY_MODEL = ...
  # 98:       FALLBACK_MODEL = ...
```

**不需要额外的 import**（它自己就是被 import 的根）。

---

### 3.2 `core/utils.py` — 通用工具函数

从 `mes1.py` 搬运以下函数（精确复制，不改函数体）：

```
搬运内容（按行号）：
  # 102-116:  terminal_print(text)
  # 640-647:  safe_path(p, cwd=None)
  # 649-665:  run_bash(command, run_in_background=False, cwd=None)
  # 667-675:  run_read(path, limit=None, cwd=None)
  # 677-685:  run_write(path, content, cwd=None)
  # 687-696:  run_edit(path, old_text, new_text)
  # 698-707:  run_find(pattern)
  # 999-1018: _normalize_todos(todos)
  # 1020-1032: run_todo_write(todos)
  # 1035-1041: extract_text(content)
  # 1044-1047: has_tool_use(content)
  # 1050-1057: call_tool_handler(handler, args, name)
  # 1199-1201: estimate_size(msgs)
  # 1203-1205: _block_type(block)
  # 1207-1214: _message_has_tool_use(msg)
  # 1216-1224: _is_tool_result_message(msg)
```

**顶部 import**：
```python
import subprocess, threading
from pathlib import Path
from config import WORKDIR, READLINE_AVAILABLE, CURRENT_TODOS
```

注意：`run_edit` 原本没有 `cwd` 参数，`run_find` 用的是 `WORKDIR`，保持原样不变。

---

### 3.3 `core/prompt.py` — System Prompt 组装

```
搬运内容（按行号）：
  # 442-447:  PROMPT_SECTIONS 字典
  # 449-472:  assemble_system_prompt(context)
  # 475-476:  _last_context_key, _last_prompt
  # 479-491:  get_system_prompt(context)
  # 494-508:  update_context(context, messages)
  # 515-519:  SUB_SYSTEM 常量
```

**顶部 import**：
```python
import json
from config import WORKDIR, MEMORY_INDEX

# 延迟导入（函数内 import）：避免 services/tools 还没初始化就被 import
```

**注意**：`assemble_system_prompt` 引用了 `mcp_clients`，`update_context` 引用了 `BUILTIN_HANDLERS`、`list_skills()`、`read_memory_index()`。统一用**函数内部延迟导入**处理：

```python
def assemble_system_prompt(context):
    from tools.mcp import mcp_clients
    # ... 原函数体（mcp_clients 那一行保持不变）
```

```python
def update_context(context, messages):
    # 延迟导入避免循环
    from tools.builtin import BUILTIN_HANDLERS
    from services.skills import list_skills
    from services.memory import read_memory_index
    from tools.mcp import mcp_clients
    # ... 原函数体
```

---

### 3.4 `core/compression.py` — s08 压缩管线

```
搬运内容（按行号）：
  # 1183-1186: CONTEXT_LIMIT, KEEP_RECENT, PERSIST_THRESHOLD, MAX_REACTIVE_RETRIES
  # 1227-1246: snip_compact(messages, max_messages=50)
  # 1249-1258: collect_tool_results(messages)  ← 注意：原文件在 micro_compact 前面
  # 1260-1268: micro_compact(messages)
  # 1271-1280: persist_large_output(tool_use_id, output)
  # 1282-1303: tool_result_budget(messages, max_bytes=200_000)
  # 1306-1313: write_transcript(messages)
  # 1315-1330: summarize_history(messages)
  # 1332-1337: compact_history(messages)
  # 1340-1349: reactive_compact(messages)
```

**顶部 import**：
```python
import json, time
from config import TRANSCRIPT_DIR, TOOL_RESULTS_DIR, client, PRIMARY_MODEL
from core.utils import estimate_size, _block_type, _message_has_tool_use, _is_tool_result_message, extract_text
```

---

### 3.5 `core/recovery.py` — s11 错误恢复

```
搬运内容（按行号）：
  # 1189-1197: ESCALATED_MAX_TOKENS, DEFAULT_MAX_TOKENS, MAX_RECOVERY_RETRIES, MAX_RETRIES, BASE_DELAY_MS, MAX_CONSECUTIVE_529, CONTINUATION_PROMPT
  # 1357-1364: RecoveryState 类
  # 1367-1376: retry_delay(attempt, retry_after=None)
  # 1379-1385: is_prompt_too_long_error(e)
  # 1388-1432: with_retry(fn, state)
```

**顶部 import**：
```python
import time, random
from config import PRIMARY_MODEL, FALLBACK_MODEL
```

---

### 3.6 `core/engine.py` — 核心循环

```
搬运内容（按行号）：
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
from config import WORKDIR, CURRENT_TODOS
from core.utils import has_tool_use, call_tool_handler, terminal_print, extract_text
from core.compression import tool_result_budget, snip_compact, micro_compact, compact_history, reactive_compact, CONTEXT_LIMIT, estimate_size
from core.recovery import RecoveryState, DEFAULT_MAX_TOKENS, ESCALATED_MAX_TOKENS, MAX_RECOVERY_RETRIES, CONTINUATION_PROMPT, with_retry, is_prompt_too_long_error
from core.prompt import assemble_system_prompt, update_context

# 函数内部延迟导入（避免循环）：
#   from services.memory import load_memories, extract_memories, consolidate_memories
#   from services.cron import consume_cron_queue
#   from services.background import inject_background_notifications, collect_background_results, should_run_background, start_background_task
#   from tools.mcp import assemble_tool_pool
#   from runtime.hooks import trigger_hooks
#   from runtime.protocol import consume_lead_inbox
```

**注意**：`agent_loop` 函数内部有很多对 services/tools/runtime 的调用，这些全部改为函数内部的延迟 import。例如：

```python
def agent_loop(messages, context):
    # 在函数内部导入
    from services.memory import load_memories, extract_memories, consolidate_memories
    from services.cron import consume_cron_queue
    from services.background import inject_background_notifications, collect_background_results, should_run_background, start_background_task
    from tools.mcp import assemble_tool_pool
    from runtime.hooks import trigger_hooks
    # ... 原函数体
```

---

### 3.7 `services/skills.py` — s07 技能系统

```
搬运内容（按行号）：
  # 123-134:  _parse_frontmatter(text)
  # 137:      SKILL_REGISTRY: dict[str, dict] = {}
  # 139-153:  _scan_skills()
  # 154:      _scan_skills()  ← 模块导入时自动执行
  # 156-160:  list_skills()
  # 1104-1109: load_skill(name)
```

**顶部 import**：
```python
import yaml
from config import SKILLS_DIR
```

---

### 3.8 `services/memory.py` — s09 记忆系统

```
搬运内容（按行号）：
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
```

**顶部 import**：
```python
import json, re, time
from config import MEMORY_DIR, MEMORY_INDEX, client, PRIMARY_MODEL
from core.utils import extract_text
```

---

### 3.9 `services/tasks.py` — s12 任务系统 + s17 扫描认领

```
搬运内容（按行号）：
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
  # 711-716:   run_create_task(subject, description="", blockedBy=None)
  # 719-732:   run_list_tasks()
  # 735-739:   run_get_task(task_id)
  # 742-743:   run_claim_task(task_id)
  # 746-747:   run_complete_task(task_id)
```

**顶部 import**：
```python
import json, time, random
from pathlib import Path
from dataclasses import dataclass, asdict
from config import TASKS_DIR
```

---

### 3.10 `services/cron.py` — s14 Cron 调度

```
搬运内容（按行号）：
  # 1757-1763: CronJob dataclass
  # 1766:      DURABLE_PATH 常量
  # 1768:      scheduled_jobs: dict[str, CronJob] = {}
  # 1769:      cron_queue: list[CronJob] = []
  # 1770:      cron_lock = threading.Lock()
  # 1771:      agent_lock = threading.Lock()
  # 1772:      _last_fired: dict[str, str] = {}
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
  # 752-757:   run_schedule_cron(cron, prompt, recurring=True, durable=True)
  # 760-770:   run_list_crons()
  # 773-774:   run_cancel_cron(job_id)
```

**顶部 import**：
```python
import json, time, threading, random
from datetime import datetime
from dataclasses import dataclass, asdict
from config import WORKDIR
```

---

### 3.11 `services/background.py` — s13 后台任务

```
搬运内容（按行号）：
  # 1677:      _bg_counter = 0
  # 1678:      background_tasks: dict[str, dict] = {}
  # 1679:      background_results: dict[str, str] = {}
  # 1680:      background_lock = threading.Lock()
  # 1683-1691: is_slow_operation(tool_name, tool_input)
  # 1694-1698: should_run_background(tool_name, tool_input)
  # 1701-1726: start_background_task(block, handlers)
  # 1729-1749: collect_background_results()
```

**顶部 import**：
```python
import threading
from core.utils import call_tool_handler

# 延迟导入：
#   from runtime.hooks import trigger_hooks  ← start_background_task 内
```

**注意**：`start_background_task` 内部调用了 `trigger_hooks("PostToolUse", ...)`，改为函数内 `from runtime.hooks import trigger_hooks`。

---

### 3.12 `tools/builtin.py` — 工具定义 + BUILTIN_HANDLERS

```
搬运内容（按行号）：
  # 523-636:  BUILTIN_TOOLS 列表 ← 完整复制
  # 1131-1167: SUB_TOOLS 列表 ← 完整复制
```

**以及两个延迟初始化函数**（这是拆分后新增的，解决循环依赖）：

```python
BUILTIN_HANDLERS: dict = {}
SUB_HANDLERS: dict = {}

def init_builtin_handlers():
    """延迟初始化：避免 tools ↔ runtime 循环导入"""
    from core.utils import run_bash, run_read, run_write, run_edit, run_find, run_todo_write
    from services.tasks import run_create_task, run_list_tasks, run_get_task, run_claim_task, run_complete_task
    from services.cron import run_schedule_cron, run_list_crons, run_cancel_cron
    from services.skills import load_skill
    from tools.subagent import spawn_subagent
    from tools.team import (run_spawn_teammate, run_send_message, run_check_inbox,
                            run_request_shutdown, run_request_plan, run_review_plan,
                            run_create_worktree, run_remove_worktree, run_keep_worktree,
                            run_connect_mcp)
    BUILTIN_HANDLERS.update({
        "bash": run_bash, "read_file": run_read, "write_file": run_write,
        "edit_file": run_edit, "glob": run_find, "todo_write": run_todo_write,
        "task": spawn_subagent, "load_skill": load_skill,
        "create_task": run_create_task, "list_tasks": run_list_tasks,
        "get_task": run_get_task, "claim_task": run_claim_task,
        "complete_task": run_complete_task,
        "schedule_cron": run_schedule_cron, "list_crons": run_list_crons,
        "cancel_cron": run_cancel_cron,
        "spawn_teammate": run_spawn_teammate, "send_message": run_send_message,
        "check_inbox": run_check_inbox,
        "request_shutdown": run_request_shutdown, "request_plan": run_request_plan,
        "review_plan": run_review_plan,
        "create_worktree": run_create_worktree, "remove_worktree": run_remove_worktree,
        "keep_worktree": run_keep_worktree,
        "connect_mcp": run_connect_mcp,
    })

def init_sub_handlers():
    """子 Agent 的受限 handler 映射"""
    from core.utils import run_bash, run_read, run_write, run_edit, run_find
    from services.tasks import run_create_task, run_list_tasks, run_get_task, run_claim_task, run_complete_task
    SUB_HANDLERS.update({
        "bash": run_bash, "read_file": run_read, "write_file": run_write,
        "edit_file": run_edit, "glob": run_find,
        "create_task": run_create_task, "list_tasks": run_list_tasks,
        "get_task": run_get_task, "claim_task": run_claim_task,
        "complete_task": run_complete_task,
    })
```

**顶部 import**：无顶层导入（全是空的 dict，延迟初始化）

---

### 3.13 `tools/subagent.py` — s06 子 Agent

```
搬运内容（按行号）：
  # 1060-1101: spawn_subagent(description)
```

**顶部 import**：
```python
from config import client, PRIMARY_MODEL
from core.utils import extract_text, has_tool_use, call_tool_handler
from core.prompt import SUB_SYSTEM

# 延迟导入（函数内）：
#   from tools.builtin import SUB_TOOLS, SUB_HANDLERS
#   from runtime.hooks import trigger_hooks
```

**注意**：`spawn_subagent` 引用了 `SUB_TOOLS` 和 `SUB_HANDLERS`，改为函数内延迟 import。

---

### 3.14 `tools/team.py` — 团队/worktree/MCP handler

```
搬运内容（按行号）：
  # 779-780:  run_spawn_teammate(name, role, prompt)
  # 783-785:  run_send_message(to, content)
  # 788-799:  run_check_inbox()
  # 804-814:  run_request_shutdown(teammate)
  # 817-819:  run_request_plan(teammate, task)
  # 823-837:  run_review_plan(request_id, approve, feedback="")
  # 842-844:  run_create_worktree(name, task_id="")
  # 847-849:  run_remove_worktree(name, discard_changes=False)
  # 852-854:  run_keep_worktree(name)
  # 857-859:  run_connect_mcp(name)
```

**顶部 import**：
```python
from config import WORKDIR
from runtime.bus import BUS

# 延迟导入（函数内）：
#   from runtime.protocol import pending_requests, new_request_id, ProtocolState, consume_lead_inbox
#   from runtime.worktree import create_worktree, remove_worktree, keep_worktree
#   from runtime.teammate import spawn_teammate_thread
#   from tools.mcp import connect_mcp
```

每个 handler 函数内按需延迟 import。例如：

```python
def run_spawn_teammate(name, role, prompt):
    from runtime.teammate import spawn_teammate_thread
    return spawn_teammate_thread(name, role, prompt)

def run_check_inbox():
    from runtime.protocol import consume_lead_inbox
    msgs = consume_lead_inbox(route_protocol=True)
    # ... 原函数体

def run_create_worktree(name, task_id=""):
    from runtime.worktree import create_worktree
    return create_worktree(name, task_id)
```

---

### 3.15 `tools/mcp.py` — s19 MCP 插件系统

```
搬运内容（按行号）：
  # 869-892:  MCPClient 类
  # 895:      mcp_clients: dict[str, MCPClient] = {}
  # 897:      _DISALLOWED_CHARS = re.compile(...)
  # 900-903:  normalize_mcp_name(name)
  # 910-927:  _mock_server_docs()
  # 930-949:  _mock_server_deploy()
  # 952-955:  MOCK_SERVERS 字典
  # 958-972:  connect_mcp(name)
  # 975-995:  assemble_tool_pool()
```

**顶部 import**：
```python
import re
from tools.builtin import BUILTIN_TOOLS, BUILTIN_HANDLERS
```

**注意**：`assemble_tool_pool` 直接 import `BUILTIN_TOOLS` 和 `BUILTIN_HANDLERS`，这是合法的——tools 层内互引，且 builtin 没有顶层循环依赖（它的 dict 是空的，由 app.py 初始化后才被调用）。

---

### 3.16 `runtime/hooks.py` — s04 钩子系统

```
搬运内容（按行号）：
  # 2402:     HOOKS = 字典
  # 2404-2406: register_hook(event, callback)
  # 2408-2414: trigger_hooks(event, *args)
  # 2418-2419: DENY_LIST, DESTRUCTIVE
  # 2421-2449: permission_hook(block)
  # 2451-2455: log_hook(block)
  # 2457-2461: large_output_hook(block, output)
  # 2463-2466: context_inject_hook(query)
  # 2468-2474: summary_hook(messages)
  # 2476-2480: 5 个 register_hook() 调用
```

**顶部 import**：
```python
from config import WORKDIR
```

**注意**：5 个 `register_hook()` 调用在模块导入时自动执行，保留原样。

---

### 3.17 `runtime/bus.py` — s15 MessageBus

```
搬运内容（按行号）：
  # 1971-1972: MAILBOX_DIR = WORKDIR / ".mailboxes"; MAILBOX_DIR.mkdir(exist_ok=True)
  # 1975-1998: MessageBus 类
  # 2001:      BUS = MessageBus()
  # 2002:      active_teammates: dict[str, bool] = {}
```

**顶部 import**：
```python
import json, time
from config import WORKDIR
```

---

### 3.18 `runtime/protocol.py` — s16 协议系统

```
搬运内容（按行号）：
  # 2010-2018: ProtocolState dataclass
  # 2021:      pending_requests: dict[str, ProtocolState] = {}
  # 2024-2025: new_request_id()
  # 2028-2051: match_response(response_type, request_id, approve)
  # 2054-2068: consume_lead_inbox(route_protocol=True)
```

**顶部 import**：
```python
import time, random
from dataclasses import dataclass, field
from runtime.bus import BUS
```

---

### 3.19 `runtime/teammate.py` — s17 队友自治 Agent

```
搬运内容（按行号）：
  # 2076-2077: IDLE_POLL_INTERVAL, IDLE_TIMEOUT
  # 2080-2137: idle_poll(agent_name, messages, name, role, worktree_context)
  # 2142-2397: spawn_teammate_thread(name, role, prompt)
```

**顶部 import**：
```python
import json, time, threading, re
from pathlib import Path
from config import client, PRIMARY_MODEL, WORKDIR, WORKTREES_DIR
from core.utils import has_tool_use, call_tool_handler
from runtime.bus import BUS, active_teammates

# 延迟导入（函数内）：
#   from runtime.protocol import ProtocolState, pending_requests, new_request_id, consume_lead_inbox
#   from services.tasks import list_tasks, claim_task, load_task, complete_task, scan_unclaimed_tasks
#   from core.utils import run_bash, run_read, run_write
```

**注意**：`spawn_teammate_thread` 是非常大的函数（~250 行），内部有大量闭包。保持完整搬运，只在函数体最前面加延迟 import。

---

### 3.20 `runtime/worktree.py` — s18 Worktree 隔离

```
搬运内容（按行号）：
  # 1562-1571: validate_worktree_name(name)
  # 1574-1583: run_git(args)
  # 1586-1592: log_event(event_type, worktree_name, task_id="")
  # 1595-1611: create_worktree(name, task_id="")
  # 1614-1619: bind_task_to_worktree(task_id, worktree_name)
  # 1622-1633: _count_worktree_changes(path)
  # 1636-1660: remove_worktree(name, discard_changes=False)
  # 1663-1670: keep_worktree(name)
```

**顶部 import**：
```python
import json, subprocess, time, re
from pathlib import Path
from config import WORKDIR, WORKTREES_DIR, VALID_WT_NAME

# 延迟导入（函数内）：
#   from services.tasks import load_task, save_task  ← bind_task_to_worktree 内
#   from services.tasks import load_task  ← remove_worktree 不需要，它只调用了 validate
```

**实际需要延迟导入的函数**：`bind_task_to_worktree` 和 `create_worktree`（如果传了 task_id）需要 `from services.tasks import load_task, save_task`。

---

### 3.21 `app.py` — 主入口

全量替换为以下内容（这是拆分后唯一的「新代码」）：

```python
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

## 四、`__init__.py` 文件

创建 4 个空的 `__init__.py`：

```
core/__init__.py       ← 空文件
services/__init__.py   ← 空文件
tools/__init__.py      ← 空文件
runtime/__init__.py    ← 空文件
```

---

## 五、延迟导入总汇

以下 9 处必须使用**函数内部 `import`**（在函数体第一行），否则会产生循环依赖：

| 文件 | 函数 | 需要延迟 import 的模块 |
|------|------|----------------------|
| `core/prompt.py` | `assemble_system_prompt()` | `tools.mcp` (mcp_clients) |
| `core/prompt.py` | `update_context()` | `tools.builtin`, `services.skills`, `services.memory`, `tools.mcp` |
| `core/engine.py` | `agent_loop()` | `services.memory`, `services.cron`, `services.background`, `tools.mcp`, `runtime.hooks` |
| `core/engine.py` | `cron_autorun_loop()` | `services.cron`, `core.prompt`, `core.utils` |
| `services/background.py` | `start_background_task()` | `runtime.hooks` |
| `tools/subagent.py` | `spawn_subagent()` | `tools.builtin` (SUB_TOOLS, SUB_HANDLERS), `runtime.hooks` |
| `tools/team.py` | 全部 handler 函数 | `runtime.protocol`, `runtime.worktree`, `runtime.teammate`, `tools.mcp` |
| `runtime/teammate.py` | `idle_poll()`, `spawn_teammate_thread()` | `runtime.protocol`, `services.tasks`, `core.utils` (run_bash/run_read/run_write) |
| `runtime/worktree.py` | `bind_task_to_worktree()`, `create_worktree()` | `services.tasks` |

---

## 六、执行步骤

1. 创建目录结构：`core/` `services/` `tools/` `runtime/` 四个文件夹
2. 创建 4 个空的 `__init__.py`
3. 按顺序创建各模块文件：`config.py` → `core/utils.py` → `core/prompt.py` → `core/compression.py` → `core/recovery.py` → `core/engine.py` → `services/*` → `tools/*` → `runtime/*` → `app.py`
4. 将原 `mes1.py` 重命名为 `mes1_backup.py`（备份）
5. 运行 `python app.py`，确保正常启动

---

## 七、验证清单

- [ ] `python app.py` 启动不报 ImportError
- [ ] 输入简单问题（如 "hello"）后 LLM 正常回复
- [ ] 技能目录扫描正常（启动时打印）
- [ ] cron 调度线程启动正常
- [ ] 钩子触发正常（日志钩子打印工具调用）
- [ ] 所有 ANSI 颜色代码保持原样 `\033[...m`
- [ ] 所有中文注释保持原样
- [ ] 没有任何业务逻辑被改动
