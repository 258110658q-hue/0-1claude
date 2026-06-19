"""工具定义 — BUILTIN_TOOLS + SUB_TOOLS + 延迟初始化 handler 映射表"""

BUILTIN_TOOLS = [
    {"name": "bash", "description": "执行 shell 命令。慢操作可设 run_in_background 放后台。",
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"},
                                     "run_in_background": {"type": "boolean"}},
                      "required": ["command"]}},
    {"name": "read_file", "description": "读取文件内容。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "将内容写入文件。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "在文件中替换精确文本一次。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "查找匹配 glob 模式的文件。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    # s05: 新增规划工具 — 只管理任务列表，不做实际操作
    {"name": "todo_write", "description": "创建并管理当前会话的任务列表。动手之前先用它列出步骤，执行过程中更新状态。",
     "input_schema": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
    {"name": "task", "description": "启动子 Agent 处理复杂子任务。只回传最终结论，中间过程全部丢弃。",
     "input_schema": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}},
    # s07: 新增技能加载工具 — 第二级，用到才加载完整内容
    {"name": "load_skill", "description": "按名称加载技能的完整内容。目录已在系统提示中，此工具获取详情。",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    # s08: 新增压缩工具 — 触发 compact_history，不在 BUILTIN_HANDLERS 中（循环内特判）
    {"name": "compact", "description": "压缩对话历史以释放上下文空间。",
     "input_schema": {"type": "object", "properties": {"focus": {"type": "string"}}}},
    # s12: 新增任务系统工具 — 持久化任务图 + 依赖管理
    {"name": "create_task", "description": "创建新任务。可指定 blockedBy 声明依赖。",
     "input_schema": {"type": "object",
                      "properties": {"subject": {"type": "string"},
                                     "description": {"type": "string"},
                                     "blockedBy": {"type": "array",
                                                   "items": {"type": "string"}}},
                      "required": ["subject"]}},
    {"name": "list_tasks", "description": "列出所有任务及其状态、认领者、依赖。",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_task", "description": "按 ID 查看任务完整 JSON 详情。",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "claim_task", "description": "认领 pending 任务（设 owner，pending→in_progress）。依赖未完成或已被认领则拒绝。",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "complete_task", "description": "完成 in_progress 任务（→completed），自动报告被解锁的下游任务。",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    # s14: 新增 cron 定时任务工具 — 闹钟式的周期性/一次性任务
    {"name": "schedule_cron", "description": "调度 cron 定时任务。cron: 五段式 '分 时 日 月 星期'。recurring: True=周期 False=一次性。durable: True=跨会话保留。",
     "input_schema": {"type": "object",
                      "properties": {"cron": {"type": "string",
                                              "description": "五段式 cron 表达式，如 '0 9 * * *'"},
                                     "prompt": {"type": "string",
                                                "description": "触发时注入给 Agent 的消息"},
                                     "recurring": {"type": "boolean"},
                                     "durable": {"type": "boolean"}},
                      "required": ["cron", "prompt"]}},
    {"name": "list_crons", "description": "列出所有已注册的 cron 定时任务。",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "cancel_cron", "description": "按 ID 取消 cron 定时任务。",
     "input_schema": {"type": "object",
                      "properties": {"job_id": {"type": "string"}},
                      "required": ["job_id"]}},
    # s15: 新增团队协作工具 — 招队友、发消息、查收件箱
    {"name": "spawn_teammate", "description": "启动后台队友 Agent。name: 队友名, role: 角色描述, prompt: 任务。",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"},
                                     "role": {"type": "string"},
                                     "prompt": {"type": "string"}},
                      "required": ["name", "role", "prompt"]}},
    {"name": "send_message", "description": "向指定 Agent 发送消息（通过 MessageBus）。",
     "input_schema": {"type": "object",
                      "properties": {"to": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["to", "content"]}},
    {"name": "check_inbox", "description": "查看 Lead 的收件箱（消费式读取，自动路由协议回复）。",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    # s16: 新增协议工具 — 关机握手 + 计划审批
    {"name": "request_shutdown", "description": "向队友发送关机请求（协议握手，等确认后才安全退出）。",
     "input_schema": {"type": "object",
                      "properties": {"teammate": {"type": "string"}},
                      "required": ["teammate"]}},
    {"name": "request_plan", "description": "要求队友对某项任务提交计划供审批。",
     "input_schema": {"type": "object",
                      "properties": {"teammate": {"type": "string"},
                                     "task": {"type": "string"}},
                      "required": ["teammate", "task"]}},
    {"name": "review_plan", "description": "审批队友提交的计划。approve: True=批准 False=拒绝。",
     "input_schema": {"type": "object",
                      "properties": {"request_id": {"type": "string"},
                                     "approve": {"type": "boolean"},
                                     "feedback": {"type": "string"}},
                      "required": ["request_id", "approve"]}},
    # s18: worktree 隔离工具
    {"name": "create_worktree", "description": "创建独立的 git worktree（独立目录 + 独立分支）。可绑定到任务。",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"},
                                     "task_id": {"type": "string"}},
                      "required": ["name"]}},
    {"name": "remove_worktree", "description": "删除 worktree。有未提交改动时默认拒绝，需 discard_changes=true 强删。",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"},
                                     "discard_changes": {"type": "boolean"}},
                      "required": ["name"]}},
    {"name": "keep_worktree", "description": "保留 worktree 供人工 review 后合并。",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"}},
                      "required": ["name"]}},
    # s19: MCP 外部工具连接
    {"name": "connect_mcp", "description": "连接到 MCP server（docs, deploy）并发现其工具。连接后工具池会动态追加 mcp__{server}__{tool} 前缀的工具。",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"}},
                      "required": ["name"]}},
]
SUB_TOOLS = [
    {"name": "bash", "description": "执行 shell 命令。慢操作可设 run_in_background 放后台。",
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"},
                                     "run_in_background": {"type": "boolean"}},
                      "required": ["command"]}},
    {"name": "read_file", "description": "读取文件内容。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "将内容写入文件。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "在文件中替换精确文本一次。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "查找匹配 glob 模式的文件。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    # s12: 子 Agent 可操作任务，但不能 spawn 孙子 Agent 或加载技能
    {"name": "create_task", "description": "创建新任务。可指定 blockedBy 声明依赖。",
     "input_schema": {"type": "object",
                      "properties": {"subject": {"type": "string"},
                                     "description": {"type": "string"},
                                     "blockedBy": {"type": "array",
                                                   "items": {"type": "string"}}},
                      "required": ["subject"]}},
    {"name": "list_tasks", "description": "列出所有任务及其状态。",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_task", "description": "按 ID 查看任务完整详情。",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "claim_task", "description": "认领 pending 任务。",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "complete_task", "description": "完成 in_progress 任务。",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
]


# ── 延迟初始化的 handler 映射表 ──
BUILTIN_HANDLERS: dict = {}
SUB_HANDLERS: dict = {}


def init_builtin_handlers():
    """延迟初始化 BUILTIN_HANDLERS：避免 tools <-> core/runtime 循环导入"""
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
    """延迟初始化 SUB_HANDLERS：子 Agent 受限 handler 映射"""
    from core.utils import run_bash, run_read, run_write, run_edit, run_find
    from services.tasks import run_create_task, run_list_tasks, run_get_task, run_claim_task, run_complete_task
    SUB_HANDLERS.update({
        "bash": run_bash, "read_file": run_read, "write_file": run_write,
        "edit_file": run_edit, "glob": run_find,
        "create_task": run_create_task, "list_tasks": run_list_tasks,
        "get_task": run_get_task, "claim_task": run_claim_task,
        "complete_task": run_complete_task,
    })
