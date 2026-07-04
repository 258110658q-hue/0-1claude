"""队友自治 Agent — s17"""
import json, time, threading, re
from pathlib import Path
from config import client, PRIMARY_MODEL, WORKTREES_DIR
from core.utils import has_tool_use, call_tool_handler, terminal_print
from runtime.bus import BUS, active_teammates

IDLE_POLL_INTERVAL = 5   # 空闲轮询间隔（秒）
IDLE_TIMEOUT = 60         # 空闲超时（秒）
def idle_poll(agent_name: str, messages: list,
              name: str, role: str,
              worktree_context: dict | None = None,
              skip_auto_claim: bool = False) -> str:
    """空闲轮询 60 秒。
    s21: skip_auto_claim=True 时跳过任务板扫描，
    确保 spawn prompt 优先于任务板上残留的旧任务。"""
    from services.tasks import scan_unclaimed_tasks, claim_task  # 延迟导入
    for _ in range(IDLE_TIMEOUT // IDLE_POLL_INTERVAL):
        time.sleep(IDLE_POLL_INTERVAL)

        # ① 检查收件箱（优先）
        inbox = BUS.read_inbox(agent_name)
        if inbox:
            # 关机请求立即处理
            for msg in inbox:
                if msg.get("type") == "shutdown_request":
                    req_id = msg.get("metadata", {}).get("request_id", "")
                    BUS.send(name, "lead", "正在收尾关机。", "shutdown_response",
                             {"request_id": req_id, "approve": True})
                    terminal_print(f"  \033[35m[协议] {name} 在 IDLE 中同意关机 "
                          f"({req_id})\033[0m")
                    return "shutdown"

            # 普通消息 → 注入上下文，回到 WORK
            messages.append({"role": "user",
                "content": "<inbox>" + json.dumps(inbox, ensure_ascii=False) + "</inbox>"})
            terminal_print(f"  \033[36m[空闲] {name} 发现收件箱消息\033[0m")
            return "work"

        # ② 扫描任务板（首次 IDLE 跳过，优先完成 spawn prompt）
        if skip_auto_claim:
            continue
        unclaimed = scan_unclaimed_tasks()
        if unclaimed:
            task = unclaimed[0]
            result = claim_task(task["id"], agent_name)
            if "已认领" in result:
                # s18: 如果有 worktree 绑定，告知队友工作目录
                # s20: IDLE 阶段直接设置 wt_ctx，不需要等到下一轮 WORK
                wt_info = ""
                if task.get("worktree"):
                    wt_path = WORKTREES_DIR / task["worktree"]
                    wt_info = f"\n工作目录: {wt_path}"
                    if worktree_context is not None:
                        worktree_context["path"] = str(wt_path)
                messages.append({"role": "user",
                    "content": f"<auto-claimed>任务 {task['id']}: "
                               f"{task['subject']}{wt_info}</auto-claimed>"})
                terminal_print(f"  \033[32m[空闲] {name} 自动认领: "
                      f"{task['subject']}\033[0m")
                return "work"
            terminal_print(f"  \033[33m[空闲] {name} 认领失败: "
                  f"{result}\033[0m")

    terminal_print(f"  \033[31m[空闲] {name} 超时 ({IDLE_TIMEOUT}s)，将关机\033[0m")
    return "timeout"
def spawn_teammate_thread(name: str, role: str, prompt: str) -> str:
    """在后台 daemon 线程里启动自治队友 Agent。"""
    from services.tasks import list_tasks, claim_task, load_task, complete_task  # 延迟导入
    from runtime.protocol import ProtocolState, pending_requests, new_request_id
    from core.utils import run_bash, run_read, run_write, run_python as _core_run_python
    if name in active_teammates:
        return f"队友 '{name}' 已存在"

    # s20: 计划审批执行门控 — 提交计划后暂停 LLM，等 Lead 审批通过才继续
    protocol_ctx = {"waiting_plan": None}

    system = (f"你是 '{name}'，一名 {role}。"
              f"用工具完成任务。通过 send_message 向 'lead' 汇报。"
              f"你可以列出和认领任务板上的任务。"
              f"如果任务绑定了 worktree，就在那个目录下工作。"
              f"提交计划后等待审批通过再动手。"
              f"检查收件箱中的协议消息（shutdown_request 等）。")

    def handle_inbox_message(name: str, msg: dict, messages: list) -> bool:
        """队友侧协议消息分发。返回 True 表示应停止循环。"""
        msg_type = msg.get("type", "message")
        meta = msg.get("metadata", {})
        req_id = meta.get("request_id", "")

        if msg_type == "shutdown_request":
            BUS.send(name, "lead", "正在收尾关机。", "shutdown_response",
                     {"request_id": req_id, "approve": True})
            terminal_print(f"  \033[35m[协议] {name} 同意关机 ({req_id})\033[0m")
            return True

        if msg_type == "plan_approval_response":
            approve = meta.get("approve", False)
            # s20: 匹配到等待中的审批请求时，清空门控，允许队友继续工作
            if req_id == protocol_ctx["waiting_plan"]:
                protocol_ctx["waiting_plan"] = None
            if approve:
                messages.append({"role": "user",
                    "content": "[计划已批准] 请按计划执行。"})
            else:
                messages.append({"role": "user",
                    "content": f"[计划被拒绝] 反馈: {msg['content']}"})
        return False

    def _teammate_submit_plan(from_name: str, plan: str) -> str:
        """队友向 Lead 提交计划审批。创建 protocol 请求，发 plan_approval_request。"""
        req_id = new_request_id()
        pending_requests[req_id] = ProtocolState(
            request_id=req_id, type="plan_approval",
            sender=from_name, target="lead",
            status="pending", payload=plan)
        BUS.send(from_name, "lead", plan, "plan_approval_request",
                 {"request_id": req_id})
        return f"计划已提交 ({req_id})。等待审批..."

    def _run_list_tasks() -> str:
        """队友侧的 list_tasks handler，显示 worktree 绑定。"""
        tasks = list_tasks()
        if not tasks:
            return "暂无任务。"
        return "\n".join(
            f"  {t.id}: {t.subject} [{t.status}]"
            + (f" owner={t.owner}" if t.owner else "")
            + (f" (wt:{t.worktree})" if t.worktree else "")
            for t in tasks)

    def run():
        # s18: worktree 上下文 — 记录当前队友的工作目录
        wt_ctx = {"path": None}

        def _wt_cwd() -> Path | None:
            p = wt_ctx["path"]
            return Path(p) if p else None

        # s18: 包装 bash/read/write，在 worktree 目录下执行
        def _run_bash(command: str) -> str:
            return run_bash(command, cwd=_wt_cwd())

        def _run_read(path: str) -> str:
            return run_read(path, cwd=_wt_cwd())

        def _run_write(path: str, content: str) -> str:
            return run_write(path, content, cwd=_wt_cwd())

        def _run_python(code: str) -> str:
            """s21: 队友侧的 run_python，自动适配 worktree 目录。"""
            return _core_run_python(code, cwd=_wt_cwd())

        def _run_claim_task(task_id: str) -> str:
            """队友侧的 claim_task handler，用队友名作为 owner。
            s18: 认领后检查任务是否有 worktree 绑定，有则切换工作目录。"""
            result = claim_task(task_id, owner=name)
            if "已认领" in result:
                task = load_task(task_id)
                if task.worktree:
                    wt_ctx["path"] = str(WORKTREES_DIR / task.worktree)
                else:
                    wt_ctx["path"] = None
            return result

        def _run_complete_task(task_id: str) -> str:
            """队友侧的 complete_task handler。
            s18: 完成后清空 worktree 上下文。"""
            result = complete_task(task_id)
            wt_ctx["path"] = None
            return result

        messages = [{"role": "user", "content": prompt}]
        sub_tools = [
            {"name": "bash", "description": "执行 shell 命令。",
             "input_schema": {"type": "object",
                              "properties": {"command": {"type": "string"}},
                              "required": ["command"]}},
            {"name": "read_file", "description": "读取文件内容。",
             "input_schema": {"type": "object",
                              "properties": {"path": {"type": "string"}},
                              "required": ["path"]}},
            {"name": "write_file", "description": "将内容写入文件。",
             "input_schema": {"type": "object",
                              "properties": {"path": {"type": "string"},
                                             "content": {"type": "string"}},
                              "required": ["path", "content"]}},
            {"name": "send_message", "description": "向其他 Agent 发送消息。",
             "input_schema": {"type": "object",
                              "properties": {"to": {"type": "string"},
                                             "content": {"type": "string"}},
                              "required": ["to", "content"]}},
            {"name": "submit_plan", "description": "向 Lead 提交计划等待审批。",
             "input_schema": {"type": "object",
                              "properties": {"plan": {"type": "string"}},
                              "required": ["plan"]}},
            # s17 新增：队友可自行操作任务板
            {"name": "list_tasks", "description": "列出任务板上所有任务及其状态、认领者。",
             "input_schema": {"type": "object", "properties": {}, "required": []}},
            {"name": "claim_task", "description": "认领 pending 任务（设为自己的 owner）。",
             "input_schema": {"type": "object",
                              "properties": {"task_id": {"type": "string"}},
                              "required": ["task_id"]}},
            {"name": "complete_task", "description": "完成自己认领的 in_progress 任务。",
             "input_schema": {"type": "object",
                              "properties": {"task_id": {"type": "string"}},
                              "required": ["task_id"]}},
            # s21: 队友也需要 run_python 做复杂分析，
            # 避免 Windows 下 python -c 多行脚本失败
            {"name": "run_python", "description": "执行 Python 代码。写入临时文件→执行→自动清理。用于数据分析、文件统计等。",
             "input_schema": {"type": "object",
                              "properties": {"code": {"type": "string"}},
                              "required": ["code"]}},
        ]
        sub_handlers = {
            "bash": _run_bash, "read_file": _run_read,
            "write_file": _run_write,
            "send_message": lambda to, content: (
                BUS.send(name, to, content), "已发送")[1],
            "submit_plan": lambda plan: _teammate_submit_plan(name, plan),
            "list_tasks": _run_list_tasks,
            "claim_task": _run_claim_task,
            "complete_task": _run_complete_task,
            "run_python": _run_python,  # s21: 安全 Python 执行
        }

        # s21: 首次 IDLE 不自动认领任务板上的旧任务，
        # 确保 spawn prompt 优先完成。
        is_first_idle = True

        # 外层循环：WORK → IDLE 交替，直到关机或超时
        while True:
            # s17: 身份重注入 — compact_history 压缩后 messages 可能只剩
            # 一条摘要，队友会忘记自己是谁。消息数 ≤ 3 时重新注入身份。
            if len(messages) <= 3:
                messages.insert(0, {"role": "user",
                    "content": f"<identity>你是 '{name}'，角色: {role}。"
                               f"继续你的工作。</identity>"})

            # ═══ WORK 阶段：inbox → LLM → 工具循环（最多 10 轮） ═══
            should_shutdown = False
            for _ in range(10):
                # 检查收件箱 → 协议分发
                inbox = BUS.read_inbox(name)
                for msg in inbox:
                    stopped = handle_inbox_message(name, msg, messages)
                    if stopped:
                        should_shutdown = True
                        break
                if should_shutdown:
                    break
                # 普通消息注入上下文
                if inbox and not should_shutdown:
                    non_protocol = [m for m in inbox
                                    if m.get("type") == "message"]
                    if non_protocol:
                        messages.append({"role": "user",
                            "content": f"<inbox>{json.dumps(non_protocol, ensure_ascii=False)}</inbox>"})

                # s20: 计划审批门控 — 提交计划后暂停 LLM，只轮询 inbox 等审批回复
                if protocol_ctx["waiting_plan"]:
                    time.sleep(IDLE_POLL_INTERVAL)
                    continue

                # LLM turn
                try:
                    response = client.messages.create(
                        model=PRIMARY_MODEL, system=system, messages=messages[-20:],
                        tools=sub_tools, max_tokens=8000)
                except Exception as e:
                    terminal_print(f"  \033[31m[队友错误] {name}: {type(e).__name__}: {e}\033[0m")
                    BUS.send(name, "lead",
                             f"[错误] API 调用失败: {type(e).__name__}", "message")
                    should_shutdown = True
                    break
                messages.append({"role": "assistant", "content": response.content})

                # s20: 用 has_tool_use 替代 stop_reason（更稳健，不依赖 API 代理行为）
                if not has_tool_use(response.content):
                    break  # WORK 阶段结束，进入 IDLE

                # 执行工具
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        # s20: submit_plan 触发门控 — 记录 request_id，停止执行
                        if block.name == "submit_plan":
                            output = _teammate_submit_plan(
                                name, block.input.get("plan", ""))
                            match = re.search(r"\((req_\d+)\)", output)
                            protocol_ctx["waiting_plan"] = (
                                match.group(1) if match else output)
                            results.append({"type": "tool_result",
                                            "tool_use_id": block.id,
                                            "content": str(output)})
                            break  # 忽略同一轮中 submit_plan 之后的其他工具调用
                        handler = sub_handlers.get(block.name)
                        output = call_tool_handler(handler, block.input, block.name)
                        results.append({"type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": str(output)})
                messages.append({"role": "user", "content": results})

                # s20: submit_plan 触发门控后跳出当前 WORK 阶段
                if protocol_ctx["waiting_plan"]:
                    break

            if should_shutdown:
                break

            # s20: 计划审批门控中 → 回外层 while，让 WORK 阶段轮询 inbox 等审批
            if protocol_ctx["waiting_plan"]:
                continue

            # ═══ IDLE 阶段：轮询 inbox + 扫描任务板（60s） ═══
            # s21: 首次 IDLE 跳过任务板扫描，优先完成 spawn prompt
            idle_result = idle_poll(name, messages, name, role, wt_ctx,
                                    skip_auto_claim=is_first_idle)
            is_first_idle = False
            if idle_result == "shutdown":
                break
            if idle_result == "timeout":
                break
            # idle_result == "work" → 回到外层 while，进入 WORK 阶段

        # ═══ SHUTDOWN：发送总结给 Lead ═══
        summary = "已关机。"
        for msg in reversed(messages):
            if msg["role"] == "assistant" and isinstance(msg["content"], list):
                for b in msg["content"]:
                    if getattr(b, "type", None) == "text":
                        summary = b.text
                        break
                else:
                    continue
                break
        BUS.send(name, "lead", summary, "result")
        active_teammates.pop(name, None)
        terminal_print(f"  \033[32m[队友] {name} 已关机\033[0m")

    active_teammates[name] = True
    threading.Thread(target=run, daemon=True).start()
    terminal_print(f"  \033[36m[队友] {name} 已启动，角色: {role}（自治模式）\033[0m")
    return f"队友 '{name}' 已启动，角色: {role}（自治模式，可自行认领任务）"
