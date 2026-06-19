#!/usr/bin/env python3
"""
s20_comprehensive.py - AI 智能体循环（完整版）— 机制很多，循环一个

一个 AI 编程智能体的全部秘密，归结为一个模式：

    while stop_reason == "tool_use":
        response = LLM(messages, tools)    # 把对话发给大模型
        执行工具                              # 模型要什么就执行什么
        把结果追加回去                         # 结果喂给下一轮

    +----------+      +-------+      +---------+
    |   用户    | ---> | 大模型 | ---> |  工具    |
    |   提问    |      |       |      |  执行    |
    +----------+      +---+---+      +----+----+
                          ^               |
                          |   工具执行结果  |
                          +---------------+
                          （循环继续）

核心思想：把工具执行的结果不断喂回给模型,
直到模型觉得问题解决了，不再调用工具为止。

版本演进:
    s01: 基础 agent_loop (bash only)
    s02: 多工具 (read/write/edit/glob) + BUILTIN_HANDLERS 分发
    s03: 三级权限管道 (deny_list → rule_match → user_approval)
    s04: 钩子系统 (HOOKS + register/trigger + 5个钩子函数)
    s05: 任务规划 (todo_write + nag reminder)
    s06: 子 Agent (task 工具 + 上下文隔离)
    s07: 技能加载 (两级知识注入：目录常驻 + 内容按需)
    s08: 上下文压缩 (四层压缩管线：便宜的先跑贵的后跑)
    s09: 持久记忆 (文件存储 + 索引注入 + 每轮提取 + 定期整理)
    s10: 分段 system prompt (PROMPT_SECTIONS + 按需拼接 + 确定性缓存)
    s11: 错误恢复 (三路径恢复：max_tokens升级续写 + prompt_too_long应急压缩 + 429/529指数退避)
    s12: 任务系统 (文件持久化任务图 + blockedBy 依赖 + claim/complete 状态机)
    s13: 后台任务 (慢操作 daemon 线程执行 + <task_notification> 通知注入)
    s14: cron 调度 (闹钟线程 + 五段式 cron + 队列自动交付 + durable 持久化)
    s15: Agent Teams (MessageBus 文件收件箱 + 队友 daemon 线程 + 收件箱注入)
    s16: Team Protocols (request_id 握手 + ProtocolState 状态机 + idle loop + 计划审批)
    s17: Autonomous Agents (空闲轮询 + 自动认领 + WORK→IDLE→SHUTDOWN 三阶段生命周期)
    s18: Worktree Isolation (git worktree 目录隔离 + 任务绑定 + 事件审计 + 安全检查)
    s19: MCP Tools (MCPClient 服务发现 + 动态工具池组装 + mcp__ 命名空间 + mock server)
    s20: Comprehensive (全部机制归位：计划审批门控 + has_tool_use + call_tool_handler + 公共函数提取 + MCP权限 + cron简化)

用法：
    pip install anthropic python-dotenv pyyaml
    ANTHROPIC_API_KEY=... python mes1.py
"""

import ast, json, os, subprocess, time, random, re, threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
import yaml
# ── readline 兼容性修复 ──────────────────────────────────
# macOS 自带的 libedit 库在处理中文输入时，按退格键会出问题,
# 这里的四行配置可以修复它。Windows 和 Linux 不受影响。
try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')  # 关闭特殊字符绑定
    readline.parse_and_bind('set input-meta on')               # 开启输入元键
    readline.parse_and_bind('set output-meta on')              # 开启输出元键
    readline.parse_and_bind('set convert-meta off')            # 关闭元键转换
except ImportError:
    readline = None  # Windows 上没有 readline

READLINE_AVAILABLE = readline is not None

from anthropic import Anthropic   # Anthropic 官方 Python SDK
from dotenv import load_dotenv    # 从 .env 文件加载环境变量

# 加载 .env 文件中的配置 (API Key、模型ID、Base URL)
# 用 __file__ 定位脚本所在目录，不受终端当前工作目录影响
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# 如果设置了自定义 BASE_URL (比如用中转平台或 DeepSeek),
# 就清除 ANTHROPIC_AUTH_TOKEN, 避免认证冲突
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"          # s07: 技能文件存放目录
TRANSCRIPT_DIR = WORKDIR / ".transcripts"              # s08: 对话抄本存档
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"  # s08: 大结果落盘目录
MEMORY_DIR = WORKDIR / ".memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
TASKS_DIR = WORKDIR / ".tasks"             # s12: 任务持久化目录
TASKS_DIR.mkdir(exist_ok=True)
WORKTREES_DIR = WORKDIR / ".worktrees"      # s18: git worktree 隔离目录
WORKTREES_DIR.mkdir(exist_ok=True)
VALID_WT_NAME = re.compile(r'^[A-Za-z0-9._-]{1,64}$')  # s18: worktree 名称校验
CURRENT_TODOS: list[dict] = []           # s05: 内存中的任务列表
# 创建 Anthropic 客户端, base_url 从环境变量读取
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
# 模型 ID 从环境变量读取 (如 claude-sonnet-4-6 或 deepseek-chat)
PRIMARY_MODEL = os.environ["MODEL_ID"]
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL_ID")  # s11: 连续 529 时切换的备用模型


# ── s20: terminal_print — 后台线程输出不打断用户输入 ──────
def terminal_print(text: str):
    """安全打印：后台线程输出时先清行、打印、再恢复用户正在输入的内容。
    主线程直接 print。"""
    if threading.current_thread() is threading.main_thread():
        print(text)
        return
    line = ""
    if READLINE_AVAILABLE:
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
    print(f"\r\033[K{text}")
    if line:
        print(f"\033[36ms19 >> \033[0m{line}", end="", flush=True)


# ── s07: 技能系统 — 两级知识注入 ──────────────────────────
# 第一级（便宜）：启动时扫描 skills/，只把名称+简介注入 SYSTEM，每轮都带 ~100 tokens
# 第二级（贵）：Agent 需要时调用 load_skill，通过 tool_result 注入完整内容 ~2000 tokens

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 SKILL.md 的 YAML 头部元数据。返回 (元数据字典, 正文)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2].strip()

# 技能注册表：启动时扫描填充，load_skill 从这里安全查找（不走文件路径，防路径遍历）
SKILL_REGISTRY: dict[str, dict] = {}

def _scan_skills():
    """启动时扫描 skills/ 目录，将名称/简介/完整内容填入注册表。"""
    if not SKILLS_DIR.exists():
        return
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "SKILL.md"
        if manifest.exists():
            raw = manifest.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            name = meta.get("name", d.name)
            desc = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
            SKILL_REGISTRY[name] = {"name": name, "description": desc, "content": raw}

_scan_skills()  # 启动时执行一次

def list_skills() -> str:
    """列出所有可用技能（名称 + 一句话简介）。"""
    if not SKILL_REGISTRY:
        return "（未找到技能）"
    return "\n".join(f"- **{s['name']}**：{s['description']}" for s in SKILL_REGISTRY.values())

# ── s09: 记忆系统 — 跨压缩、跨会话的持久化知识 ──────────
# 三层操作：加载（每轮注入相关记忆）、写入（每轮结束提取新记忆）、整理（定期去重）
# 存储：.memory/*.md 文件 + MEMORY.md 索引

MEMORY_TYPES = ["user", "feedback", "project", "reference"]
CONSOLIDATE_THRESHOLD = 10   # 记忆文件数达到此值触发整理

def _parse_memory_frontmatter(text: str) -> tuple[dict, str]:
    """解析记忆文件的 YAML frontmatter（不用 yaml 库，避免依赖）。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2].strip()

def write_memory_file(name: str, mem_type: str, description: str, body: str):
    """写单个记忆文件（YAML frontmatter + markdown 正文），写完后重建索引。"""
    MEMORY_DIR.mkdir(exist_ok=True)
    slug = name.lower().replace(" ", "-").replace("/", "-")
    filepath = MEMORY_DIR / f"{slug}.md"
    filepath.write_text(
        f"---\nname: {name}\ndescription: {description}\ntype: {mem_type}\n---\n\n{body}\n",
        encoding="utf-8"
    )
    _rebuild_index()
    return filepath

def _rebuild_index():
    """扫描 .memory/ 下所有 .md 文件，重建 MEMORY.md 索引。"""
    MEMORY_DIR.mkdir(exist_ok=True)
    lines = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_memory_frontmatter(raw)
        name = meta.get("name", f.stem)
        desc = meta.get("description", body.split("\n")[0][:80])
        lines.append(f"- [{name}]({f.name}) — {desc}")
    MEMORY_INDEX.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")

def read_memory_index() -> str:
    """读 MEMORY.md 索引（注入 SYSTEM，每轮都带）。"""
    if not MEMORY_INDEX.exists():
        return ""
    text = MEMORY_INDEX.read_text(encoding="utf-8").strip()
    return text if text else ""

def read_memory_file(filename: str) -> str | None:
    """读单个记忆文件的完整内容。"""
    path = MEMORY_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")

def list_memory_files() -> list[dict]:
    """列出所有记忆文件的元数据（名称、描述、类型、正文）。"""
    result = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_memory_frontmatter(raw)
        result.append({
            "filename": f.name,
            "name": meta.get("name", f.stem),
            "description": meta.get("description", ""),
            "type": meta.get("type", "user"),
            "body": body,
        })
    return result

def select_relevant_memories(messages: list, max_items: int = 5) -> list[str]:
    """用 LLM 侧查询选出跟当前对话最相关的记忆文件名。
    失败时降级为关键词匹配。"""
    files = list_memory_files()
    if not files:
        return []

    # 收集最近的用户文本作为上下文
    recent_texts = []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    str(getattr(b, "text", "")) for b in content
                    if getattr(b, "type", None) == "text"
                )
            if isinstance(content, str):
                recent_texts.append(content)
            if len(recent_texts) >= 3:
                break
    recent = " ".join(reversed(recent_texts))[:2000]

    if not recent.strip():
        return []

    # 构建记忆目录供 LLM 选择
    catalog_lines = [f"{i}: {f['name']} — {f['description']}" for i, f in enumerate(files)]
    catalog = "\n".join(catalog_lines)

    prompt = (
        "根据最近的对话和下面的记忆目录，选出明显相关的记忆的索引。"
        "只返回 JSON 整数数组，如 [0, 3]。都不相关则返回 []。\n\n"
        f"最近对话：\n{recent}\n\n"
        f"记忆目录：\n{catalog}"
    )

    try:
        response = client.messages.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        text = extract_text(response.content).strip()
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            indices = json.loads(match.group())
            selected = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(files):
                    selected.append(files[idx]["filename"])
                    if len(selected) >= max_items:
                        break
            return selected
    except Exception:
        pass

    # 降级：关键词匹配 name + description
    keywords = [w.lower() for w in recent.split() if len(w) > 3]
    selected = []
    for f in files:
        text = (f["name"] + " " + f["description"]).lower()
        if any(kw in text for kw in keywords):
            selected.append(f["filename"])
            if len(selected) >= max_items:
                break
    return selected

def load_memories(messages: list) -> str:
    """加载相关记忆内容，包装为 <relevant_memories> 标签。"""
    selected_files = select_relevant_memories(messages)
    if not selected_files:
        return ""

    parts = ["<relevant_memories>"]
    for filename in selected_files:
        content = read_memory_file(filename)
        if content:
            parts.append(content)
    parts.append("</relevant_memories>")
    return "\n\n".join(parts)

def extract_memories(messages: list):
    """从最近对话中提取新记忆，写入 .memory/。每轮结束后调用。"""
    # 收集最近 10 条消息的文本
    dialogue_parts = []
    for msg in messages[-10:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(getattr(b, "text", "")) for b in content
                if getattr(b, "type", None) == "text"
            )
        if isinstance(content, str) and content.strip():
            dialogue_parts.append(f"{role}: {content}")
    dialogue = "\n".join(dialogue_parts)

    if not dialogue.strip():
        return

    # 检查已有记忆，避免重复
    existing = list_memory_files()
    existing_desc = "\n".join(
        f"- {m['name']}: {m['description']}" for m in existing
    ) if existing else "（无）"

    prompt = (
        "从以下对话中提取用户偏好、约束或项目事实。\n"
        "返回 JSON 数组。每项：{name, type, description, body}。\n"
        "- name: 短的 kebab-case 标识符（如 'user-preference-tabs'）\n"
        "- type: 类型，'user'（用户偏好）/ 'feedback'（行事指引）/ "
        "'project'（项目事实）/ 'reference'（外部指针）\n"
        "- description: 一行摘要，用于索引查找\n"
        "- body: markdown 格式的完整详情\n"
        "如果没有新内容或已有记忆已覆盖，返回 []。\n\n"
        f"已有记忆：\n{existing_desc}\n\n"
        f"对话：\n{dialogue[:4000]}"
    )

    try:
        response = client.messages.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        text = extract_text(response.content).strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if not match:
            return
        items = json.loads(match.group())
        if not items:
            return
        count = 0
        for mem in items:
            name = mem.get("name", f"memory_{int(time.time())}")
            mem_type = mem.get("type", "user")
            desc = mem.get("description", "")
            body = mem.get("body", "")
            if desc and body:
                write_memory_file(name, mem_type, desc, body)
                count += 1
        if count:
            print(f"\n\033[33m[记忆: 提取了 {count} 条新记忆]\033[0m")
    except Exception:
        pass

def consolidate_memories():
    """记忆文件数达到阈值时，让 LLM 去重合并、删除过时记忆。"""
    files = list_memory_files()
    if len(files) < CONSOLIDATE_THRESHOLD:
        return

    catalog = "\n\n".join(
        f"## {f['filename']}\nname: {f['name']}\ndescription: {f['description']}\n{f['body']}"
        for f in files
    )

    prompt = (
        "整理以下记忆文件。规则：\n"
        "1. 合并内容重复的记忆\n"
        "2. 删除已过时或被新记忆覆盖的\n"
        "3. 总数控制在 30 条以内\n"
        "4. 优先保留用户偏好类记忆\n"
        "返回 JSON 数组。每项：{name, type, description, body}。\n\n"
        f"{catalog[:16000]}"
    )

    try:
        response = client.messages.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        text = extract_text(response.content).strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if not match:
            return
        items = json.loads(match.group())

        # 删除所有旧记忆文件（保留 MEMORY.md）
        for f in MEMORY_DIR.glob("*.md"):
            if f.name != "MEMORY.md":
                f.unlink()

        for mem in items:
            name = mem.get("name", f"memory_{int(time.time())}")
            mem_type = mem.get("type", "user")
            desc = mem.get("description", "")
            body = mem.get("body", "")
            if desc and body:
                write_memory_file(name, mem_type, desc, body)

        print(f"\n\033[33m[记忆: 整理 {len(files)} → {len(items)} 条]\033[0m")
    except Exception:
        pass

# ── s10: System Prompt 分段组装 + 缓存 ─────────────────
# s09 的 build_system() 是一大段字符串拼出来，加新能力就得改函数体。
# s10 拆成独立段落（PROMPT_SECTIONS），运行时按真实状态按需拼接。
# s19: 去掉 json.dumps 缓存——connect_mcp 后工具池变了，缓存会过时。

PROMPT_SECTIONS = {
    "identity": f"你是在 {WORKDIR} 工作的编程智能体。",
    "memory_instruction": "相关记忆会在每轮自动注入。当用户说'记住'或表达明确偏好时，提取为记忆。",
    "skills_instruction": "需要时使用 load_skill 获取技能的完整内容。",
    "mcp_instruction": "使用 connect_mcp 连接外部 MCP server。连接后 MCP 工具以 mcp__{server}__{tool} 格式可用。",
}

def assemble_system_prompt(context: dict) -> str:
    """根据 context 真实状态按需拼接 prompt 段落。
    s19: 动态添加已连接的 MCP server 列表。"""
    sections = [PROMPT_SECTIONS["identity"]]

    # 始终加载：技能目录（扫描结果已在 context 中）
    skills_catalog = context.get("skills_catalog", "")
    if skills_catalog:
        sections.append(f"可用技能：\n{skills_catalog}")
    sections.append(PROMPT_SECTIONS["skills_instruction"])

    # 按需加载：MEMORY.md 有内容才加记忆段落
    memories = context.get("memories", "")
    if memories:
        sections.append(f"可用记忆：\n{memories}")
    sections.append(PROMPT_SECTIONS["memory_instruction"])

    # s19: MCP — 已连接的 server 列表
    sections.append(PROMPT_SECTIONS["mcp_instruction"])
    mcp_names = list(mcp_clients.keys())
    if mcp_names:
        sections.append(f"已连接的 MCP server: {', '.join(mcp_names)}")

    return "\n\n".join(sections)


_last_context_key = None
_last_prompt = None


def get_system_prompt(context: dict) -> str:
    """缓存包装：context 没变就返回缓存，避免重复拼接字符串。

    用 json.dumps 做确定性序列化，不用 Python 的 hash()——
    hash() 有进程随机化，且遇到 dict/list 会报 unhashable type。
    """
    global _last_context_key, _last_prompt
    key = json.dumps(context, sort_keys=True, ensure_ascii=False, default=str)
    if key == _last_context_key and _last_prompt:
        return _last_prompt
    _last_context_key = key
    _last_prompt = assemble_system_prompt(context)
    return _last_prompt


def update_context(context: dict, messages: list) -> dict:
    """从真实状态派生 context：工具是否存在、记忆文件是否存在、MCP 连接状态。
    判断依据是真实状态，不是消息里的关键词。"""
    memories = ""
    if MEMORY_INDEX.exists():
        content = MEMORY_INDEX.read_text(encoding="utf-8").strip()
        if content:
            memories = content
    return {
        "enabled_tools": list(BUILTIN_HANDLERS.keys()),
        "workspace": str(WORKDIR),
        "memories": memories,
        "skills_catalog": list_skills(),
        "mcp_servers": list(mcp_clients.keys()),  # s19
    }

# s10: SYSTEM 不再是一大段硬编码字符串，而是 PROMPT_SECTIONS 按需拼装。
# s19: agent_loop 不再使用 get_system_prompt 缓存（工具池动态变化后缓存失效），
# 但队列处理器和子 Agent 仍可能用到。

# s06: 子 Agent 的独立系统提示 — 禁止再委派，只回传结论
SUB_SYSTEM = (
    f"你是在 {WORKDIR} 工作的编程智能体。"
    "完成交给你的任务，然后返回简洁的总结。"
    "不要进一步委派。"
)

# ── s19: 内置工具定义 (BUILTIN_TOOLS + BUILTIN_HANDLERS) ──
# MCP 工具在运行时通过 assemble_tool_pool 动态追加
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


# ── 工具执行函数 ───────────────────────────────────────
def safe_path(p: str, cwd: Path = None) -> Path:
    """安全路径解析：禁止访问工作目录之外的路径。
    s18: 可选 cwd 参数，队友在 worktree 下执行时传入 worktree 路径。"""
    base = cwd or WORKDIR
    path = (base / p).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"路径越界: {p}")
    return path

def run_bash(command: str, run_in_background: bool = False,
             cwd: Path = None) -> str:
    # run_in_background 由 agent_loop 分发处理，这里只负责同步执行
    # s18: 可选 cwd 参数，队友在 worktree 下执行时传入 worktree 路径
    try:
        r = subprocess.run(
            command,            # 要执行的命令，比如"ls -l"、"python test.py"
            shell=True,         # 允许执行带管道、通配符的复杂命令
            cwd=cwd or WORKDIR, # s18: 支持在 worktree 目录下执行
            capture_output=True,# 捕获命令的输出，返回给 AI
            text=True,          # 输出为字符串格式
            timeout=120         # 最多跑 120 秒，防止死循环
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（无输出）"
    except subprocess.TimeoutExpired:
        return "错误: 命令超时 (120s)"

def run_read(path: str, limit: int | None = None, cwd: Path = None) -> str:
    """s18: 可选 cwd 参数，队友在 worktree 下读取。"""
    try:
        lines = safe_path(path, cwd).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... （还有 {len(lines) - limit} 行）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"

def run_write(path: str, content: str, cwd: Path = None) -> str:
    """s18: 可选 cwd 参数，队友在 worktree 下写入。"""
    try:
        file_path = safe_path(path, cwd)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"已写入 {len(content)} 字节到 {path}"
    except Exception as e:
        return f"错误: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"错误: 在 {path} 中未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"已编辑 {path}"
    except Exception as e:
        return f"错误: {e}"

def run_find(pattern: str) -> str:
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "（无匹配）"
    except Exception as e:
        return f"错误: {e}"

# ── s12: 任务工具 handler — Agent 通过这 5 个工具操作任务图 ──

def run_create_task(subject: str, description: str = "",
                    blockedBy: list[str] | None = None) -> str:
    task = create_task(subject, description, blockedBy)
    deps = f" (blockedBy: {', '.join(blockedBy)})" if blockedBy else ""
    print(f"  \033[34m[创建任务] {task.subject}{deps}\033[0m")
    return f"已创建 {task.id}: {task.subject}{deps}"


def run_list_tasks() -> str:
    tasks = list_tasks()
    if not tasks:
        return "暂无任务。使用 create_task 添加。"
    lines = []
    for t in tasks:
        icon = {"pending": "○", "in_progress": "●",
                "completed": "✓"}.get(t.status, "?")
        deps = f" (blockedBy: {', '.join(t.blockedBy)})" if t.blockedBy else ""
        owner = f" [{t.owner}]" if t.owner else ""
        wt = f" (wt:{t.worktree})" if t.worktree else ""
        lines.append(f"  {icon} {t.id}: {t.subject} "
                     f"[{t.status}]{owner}{deps}{wt}")
    return "\n".join(lines)


def run_get_task(task_id: str) -> str:
    try:
        return get_task(task_id)
    except FileNotFoundError:
        return f"错误: 任务 {task_id} 未找到"


def run_claim_task(task_id: str) -> str:
    return claim_task(task_id, owner="agent")


def run_complete_task(task_id: str) -> str:
    return complete_task(task_id)


# ── s14: cron 工具 handler — Agent 通过这 3 个工具管理定时任务 ──

def run_schedule_cron(cron: str, prompt: str,
                      recurring: bool = True, durable: bool = True) -> str:
    result = schedule_job(cron, prompt, recurring, durable)
    if isinstance(result, str):
        return f"错误: {result}"
    return f"已调度 {result.id}: '{cron}' → {prompt}"


def run_list_crons() -> str:
    with cron_lock:
        jobs = list(scheduled_jobs.values())
    if not jobs:
        return "暂无 cron 任务。使用 schedule_cron 添加。"
    lines = []
    for j in jobs:
        tag = "周期" if j.recurring else "一次性"
        dur = "持久化" if j.durable else "会话级"
        lines.append(f"  {j.id}: '{j.cron}' → {j.prompt[:40]} [{tag}, {dur}]")
    return "\n".join(lines)


def run_cancel_cron(job_id: str) -> str:
    return cancel_job(job_id)


# ── s15: 团队工具 handler — Lead 通过这 3 个工具管理团队 ──

def run_spawn_teammate(name: str, role: str, prompt: str) -> str:
    return spawn_teammate_thread(name, role, prompt)


def run_send_message(to: str, content: str) -> str:
    BUS.send("lead", to, content)
    return f"已发送给 {to}"


def run_check_inbox() -> str:
    """查看收件箱——统一走 consume_lead_inbox 路由协议回复。"""
    msgs = consume_lead_inbox(route_protocol=True)
    if not msgs:
        return "（收件箱为空）"
    lines = []
    for m in msgs:
        meta = m.get("metadata", {})
        req_id = meta.get("request_id", "")
        tag = f" [{m['type']} req:{req_id}]" if req_id else f" [{m['type']}]"
        lines.append(f"  [{m['from']}]{tag} {m['content'][:200]}")
    return "\n".join(lines)


# ── s16: 协议工具 handler — Lead 用这 3 个工具管理团队协议 ──

def run_request_shutdown(teammate: str) -> str:
    """向队友发送关机请求（协议握手）。"""
    req_id = new_request_id()
    pending_requests[req_id] = ProtocolState(
        request_id=req_id, type="shutdown",
        sender="lead", target=teammate,
        status="pending", payload="")
    BUS.send("lead", teammate, "请收尾后关机。", "shutdown_request",
             {"request_id": req_id})
    print(f"  \033[35m[协议] shutdown_request → {teammate} ({req_id})\033[0m")
    return f"已向 {teammate} 发送关机请求 (req: {req_id})"


def run_request_plan(teammate: str, task: str) -> str:
    """让队友提交计划以供审批。"""
    BUS.send("lead", teammate, f"请为以下任务提交计划: {task}", "message")
    return f"已要求 {teammate} 提交计划"


def run_review_plan(request_id: str, approve: bool, feedback: str = "") -> str:
    """审批队友提交的计划。approve=True 批准，False 拒绝。"""
    state = pending_requests.get(request_id)
    if not state:
        return f"未找到请求 {request_id}"
    if state.status != "pending":
        return f"请求 {request_id} 已 {state.status}"
    state.status = "approved" if approve else "rejected"
    BUS.send("lead", state.sender,
             feedback or ("已批准" if approve else "已拒绝"),
             "plan_approval_response",
             {"request_id": request_id, "approve": approve})
    icon = "✓" if approve else "✗"
    print(f"  \033[32m[协议] 计划 {icon} ({request_id})\033[0m")
    return f"计划已{'批准' if approve else '拒绝'} ({request_id})"


# ── s18: Worktree 工具 handler — Lead 用这 3 个工具管理隔离目录 ──

def run_create_worktree(name: str, task_id: str = "") -> str:
    """创建 git worktree + 可选绑定任务。"""
    return create_worktree(name, task_id)


def run_remove_worktree(name: str, discard_changes: bool = False) -> str:
    """删除 worktree。有未提交改动时默认拒绝。"""
    return remove_worktree(name, discard_changes)


def run_keep_worktree(name: str) -> str:
    """保留 worktree 分支供人工 review。"""
    return keep_worktree(name)


def run_connect_mcp(name: str) -> str:
    """连接到 MCP server 并发现其工具。"""
    return connect_mcp(name)


# ── s19: MCP 插件系统 — 外部工具通过标准协议接入 ──────────
# s01-s18 所有工具都是手写的。s19 引入 MCP (Model Context Protocol)：
# 外部服务只要实现 tools/list + tools/call，Agent 就能发现和调用。
# MCPClient 模拟服务端（教学版用 Python 函数，真实版用 stdio JSON-RPC）。
# assemble_tool_pool 把内置工具和 MCP 工具动态组装成统一工具池。
# mcp__{server}__{tool} 前缀避免不同 server 的工具名冲突。

class MCPClient:
    """MCP 客户端：模拟 tools/list（服务发现）和 tools/call（远程调用）。
    教学版用 Python 函数模拟 server；真实 CC 通过子进程 stdin/stdout 发 JSON-RPC。"""

    def __init__(self, name: str):
        self.name = name
        self.tools: list[dict] = []           # 从 server 发现的工具列表
        self._handlers: dict[str, callable] = {}  # 工具名 → 处理函数

    def register(self, tool_defs: list[dict],
                 handlers: dict[str, callable]):
        """模拟 tools/list：注册这个 server 提供的工具和对应处理器。"""
        self.tools = tool_defs
        self._handlers = handlers

    def call_tool(self, tool_name: str, args: dict) -> str:
        """模拟 tools/call：调用 server 上的工具并返回结果。"""
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"MCP 错误: 未知工具 '{tool_name}'"
        try:
            return handler(**args)
        except Exception as e:
            return f"MCP 错误: {e}"


mcp_clients: dict[str, MCPClient] = {}   # server_name → MCPClient

_DISALLOWED_CHARS = re.compile(r'[^a-zA-Z0-9_-]')


def normalize_mcp_name(name: str) -> str:
    """规范化 MCP server/工具 名称：非 [a-zA-Z0-9_-] 的字符替换为 _。
    防止特殊字符导致命名冲突或注入。"""
    return _DISALLOWED_CHARS.sub('_', name)


# ── Mock MCP Server 工厂函数 ──────────────────────────────
# 教学版用 mock 模拟外部服务，不依赖真实外部进程。
# 工具描述中标注 (readOnly) 或 (destructive)，真实 CC 用 tool annotations 驱动权限系统。

def _mock_server_docs():
    """模拟「文档知识库」MCP server。"""
    client = MCPClient("docs")
    client.register(
        tool_defs=[
            {"name": "search", "description": "搜索文档。 (readOnly)",
             "inputSchema": {"type": "object",
                             "properties": {"query": {"type": "string"}},
                             "required": ["query"]}},
            {"name": "get_version", "description": "获取 API 版本。 (readOnly)",
             "inputSchema": {"type": "object", "properties": {},
                             "required": []}},
        ],
        handlers={
            "search": lambda query: f"[docs] 找到 3 条关于 '{query}' 的结果",
            "get_version": lambda: "[docs] API v2.1.0",
        })
    return client


def _mock_server_deploy():
    """模拟「部署系统」MCP server。"""
    client = MCPClient("deploy")
    client.register(
        tool_defs=[
            {"name": "trigger",
             "description": "触发部署。 (destructive — 真实 CC 需要权限确认)",
             "inputSchema": {"type": "object",
                             "properties": {"service": {"type": "string"}},
                             "required": ["service"]}},
            {"name": "status", "description": "查看部署状态。 (readOnly)",
             "inputSchema": {"type": "object",
                             "properties": {"service": {"type": "string"}},
                             "required": ["service"]}},
        ],
        handlers={
            "trigger": lambda service: f"[deploy] 已触发: {service}",
            "status": lambda service: f"[deploy] {service}: 运行中 (v1.4.2)",
        })
    return client


MOCK_SERVERS = {
    "docs": _mock_server_docs,
    "deploy": _mock_server_deploy,
}


def connect_mcp(name: str) -> str:
    """连接到 MCP server，发现其工具并加入全局 mcp_clients。
    连接后 assemble_tool_pool 会动态追加 mcp__{server}__{tool} 工具。"""
    if name in mcp_clients:
        return f"MCP server '{name}' 已连接"
    factory = MOCK_SERVERS.get(name)
    if not factory:
        available = ", ".join(MOCK_SERVERS.keys())
        return f"未知 server '{name}'。可用: {available}"
    mcp_client = factory()
    mcp_clients[name] = mcp_client
    tool_names = [t["name"] for t in mcp_client.tools]
    print(f"  \033[31m[mcp] 已连接: {name} → {tool_names}\033[0m")
    return (f"已连接 MCP server '{name}'。"
            f"发现 {len(mcp_client.tools)} 个工具: {', '.join(tool_names)}")


def assemble_tool_pool() -> tuple[list[dict], dict]:
    """动态组装工具池：内置工具 + 所有已连接 MCP server 的工具。
    MCP 工具以 mcp__{server}__{tool} 命名，避免不同 server 间冲突。
    每次调用都重新构建——connect_mcp 后工具池变化，缓存会过时。"""
    tools = list(BUILTIN_TOOLS)
    handlers = dict(BUILTIN_HANDLERS)
    for server_name, mcp_client in mcp_clients.items():
        safe_server = normalize_mcp_name(server_name)
        for tool_def in mcp_client.tools:
            safe_tool = normalize_mcp_name(tool_def["name"])
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            tools.append({
                "name": prefixed,
                "description": tool_def.get("description", ""),
                "input_schema": tool_def.get("inputSchema", {}),
            })
            # 闭包默认参数绑定当前的 mcp_client 和 tool_name
            handlers[prefixed] = (
                lambda *, c=mcp_client, t=tool_def["name"], **kw:
                    c.call_tool(t, kw))
    return tools, handlers


# ── s05: todo_write 工具 — 纯规划，不做任何实际操作 ──────
def _normalize_todos(todos):
    """校验 todo 格式：必须是列表，每项必须有 content 和 status"""
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "错误: todos 必须是列表或 JSON 数组字符串"
    if not isinstance(todos, list):
        return None, "错误: todos 必须是列表"
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return None, f"错误: todos[{i}] 必须是对象"
        if "content" not in t or "status" not in t:
            return None, f"错误: todos[{i}] 缺少 'content' 或 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return None, f"错误: todos[{i}] 状态 '{t['status']}' 无效"
    return todos, None

def run_todo_write(todos: list) -> str:
    """s05: 更新任务列表并在终端渲染看板"""
    global CURRENT_TODOS
    todos, error = _normalize_todos(todos)
    if error:
        return error
    CURRENT_TODOS = todos
    lines = ["\n\033[33m## 当前任务\033[0m"]
    for t in CURRENT_TODOS:
        icon = {"pending": " ", "in_progress": "\033[36m▸\033[0m", "completed": "\033[32m✓\033[0m"}[t["status"]]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))
    return f"已更新 {len(CURRENT_TODOS)} 个任务"

# ── s06: 子 Agent — 全新上下文，只回传结论 ─────────────────
def extract_text(content) -> str:
    """从消息内容块中提取纯文本"""
    if not isinstance(content, list):
        return str(content)
    return "\n".join(getattr(b, "text", "") for b in content
                     if getattr(b, "type", None) == "text")


# ── s20: 辅助函数 — has_tool_use + call_tool_handler ──────
def has_tool_use(content) -> bool:
    """检查响应中是否包含 tool_use 块。不依赖 stop_reason（不同 API 代理行为不同）。"""
    return any(getattr(block, "type", None) == "tool_use"
               for block in content)


def call_tool_handler(handler, args: dict, name: str) -> str:
    """安全调用工具 handler：handler 不存在或参数不匹配时返回错误消息，不抛异常。"""
    if not handler:
        return f"未知工具: {name}"
    try:
        return handler(**(args or {}))
    except TypeError as e:
        return f"参数错误: {e}"


def spawn_subagent(description: str) -> str:
    """s06: 派生子 Agent，全新上下文，只回传结论"""
    print(f"\n\033[35m[子 Agent 已启动]\033[0m")
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
                print(f"  \033[90m[子] {block.name}: {str(output)[:100]}\033[0m")
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
    print(f"\033[35m[子 Agent 完成]\033[0m")
    return result

# ── s07: load_skill — 按需加载技能完整内容 ────────────────
def load_skill(name: str) -> str:
    """从注册表查找技能并返回完整内容。不走文件路径，防路径遍历。"""
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return f"未找到技能: {name}"
    return skill["content"]

# s02: 工具分发映射（s01 是硬编码 run_bash，现在改为查表）
BUILTIN_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_find, "todo_write": run_todo_write,
    "task": spawn_subagent, "load_skill": load_skill,  # s06, s07
    "create_task": run_create_task, "list_tasks": run_list_tasks,  # s12
    "get_task": run_get_task, "claim_task": run_claim_task,
    "complete_task": run_complete_task,
    "schedule_cron": run_schedule_cron, "list_crons": run_list_crons,  # s14
    "cancel_cron": run_cancel_cron,
    "spawn_teammate": run_spawn_teammate, "send_message": run_send_message,  # s15
    "check_inbox": run_check_inbox,
    "request_shutdown": run_request_shutdown, "request_plan": run_request_plan,  # s16
    "review_plan": run_review_plan,
    "create_worktree": run_create_worktree, "remove_worktree": run_remove_worktree,  # s18
    "keep_worktree": run_keep_worktree,
    "connect_mcp": run_connect_mcp,  # s19
}

# ── s06: 子 Agent 的受限工具箱（5 个工具，无 task/load_skill，禁止递归） ──
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
# 注意：没有 task 和 load_skill — 禁止子 Agent 再 spawn 孙子 Agent 或加载技能

SUB_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_find,
    "create_task": run_create_task, "list_tasks": run_list_tasks,  # s12
    "get_task": run_get_task, "claim_task": run_claim_task,
    "complete_task": run_complete_task,
}

# ── s08: 四层上下文压缩管线 ─────────────────────────────────
# 核心设计：便宜的先跑，贵的后跑。
# L1 snip_compact → L2 micro_compact → L3 tool_result_budget → L4 compact_history
# 前三层 0 API 调用，第四层 1 API 调用。API 报错时触发应急压缩。

CONTEXT_LIMIT = 50000        # 字符数阈值，超过则触发 L4 自动摘要
KEEP_RECENT = 3              # L2 micro: 保留最近 N 条 tool_result 的完整内容
PERSIST_THRESHOLD = 30000    # L3 budget: 单条结果超过此大小就落盘
MAX_REACTIVE_RETRIES = 1     # 应急压缩最多重试次数

# ── s11: 错误恢复常量 ──────────────────────────────────
ESCALATED_MAX_TOKENS = 64000           # max_tokens 升级目标
DEFAULT_MAX_TOKENS = 8000              # 默认输出 token 上限
MAX_RECOVERY_RETRIES = 3               # 续写最多尝试次数
MAX_RETRIES = 10                       # 429/529 最多重试次数
BASE_DELAY_MS = 500                    # 指数退避基础延迟（毫秒）
MAX_CONSECUTIVE_529 = 3                # 连续 529 后切换备用模型
CONTINUATION_PROMPT = (
    "输出 token 限制已达。直接继续——不要道歉，不要复述。从中断处接着写。"
)

def estimate_size(msgs):
    """估算消息列表的字符大小（非精确 token，但够用）。"""
    return len(str(msgs))

def _block_type(block):
    """获取块的 type 字段，兼容 dict 和对象两种格式。"""
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

def _message_has_tool_use(msg):
    """检查 assistant 消息是否包含 tool_use 块。"""
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(_block_type(b) == "tool_use" for b in content)

def _is_tool_result_message(msg):
    """检查 user 消息是否包含 tool_result 块。"""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result"
               for b in content)

# ═══ L1: snip_compact — 裁剪中间消息 ═══
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

# ═══ L2: micro_compact — 旧工具结果占位 ═══
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

# ═══ L3: tool_result_budget — 大结果落盘 ═══
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

# ═══ L4: compact_history — LLM 全量摘要 ═══
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
    print(f"[对话抄本已保存: {transcript_path}]")
    summary = summarize_history(messages)
    return [{"role": "user", "content": f"[已压缩]\n\n{summary}"}]

# ═══ 应急: reactive_compact ═══
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


# ── s11: 错误恢复系统 — 三种恢复路径 + 指数退避 ──────
# 路径1: max_tokens → 8K→64K 升级 → 续写提示（最多3次）
# 路径2: prompt_too_long → reactive_compact → 重试（1次）
# 路径3: 429/529 → 指数退避 + 抖动（最多10次）→ 连续529切换备用模型

class RecoveryState:
    """追踪一轮 agent_loop 中的恢复尝试状态。"""
    def __init__(self):
        self.has_escalated = False              # 是否已从 8K 升级到 64K
        self.recovery_count = 0                  # 续写次数（最多 3）
        self.consecutive_529 = 0                 # 连续 529 过载计数
        self.has_attempted_reactive_compact = False  # 是否已尝试应急压缩
        self.current_model = PRIMARY_MODEL       # 当前使用的模型（529 后可切换）


def retry_delay(attempt, retry_after=None):
    """指数退避 + 随机抖动。Retry-After header 优先。

    公式: min(500 × 2^attempt, 32000) / 1000 秒 + 0~25% 随机抖动。
    """
    if retry_after:
        return retry_after
    base = min(BASE_DELAY_MS * (2 ** attempt), 32000) / 1000
    jitter = random.uniform(0, base * 0.25)
    return base + jitter


def is_prompt_too_long_error(e: Exception) -> bool:
    """判断异常是否属于上下文超限（兼容多种 API 的错误消息格式）。"""
    msg = str(e).lower()
    return (("prompt" in msg and "long" in msg)
            or "prompt_is_too_long" in msg
            or "context_length_exceeded" in msg
            or "max_context_window" in msg)


def with_retry(fn, state: RecoveryState):
    """对 429/529 瞬态错误做指数退避重试。

    非瞬态错误（如 prompt_too_long）直接往外抛，
    交给外层 try/except 处理。"""
    for attempt in range(MAX_RETRIES):
        try:
            result = fn()
            state.consecutive_529 = 0  # 调用成功，重置计数器
            return result
        except Exception as e:
            name = type(e).__name__
            msg = str(e).lower()

            # 429 限流 → 指数退避
            if "ratelimit" in name.lower() or "429" in msg:
                delay = retry_delay(attempt)
                print(f"  \033[33m[429 限流] 重试 {attempt+1}/{MAX_RETRIES},"
                      f" 等待 {delay:.1f}s\033[0m")
                time.sleep(delay)
                continue

            # 529 过载 → 指数退避 + 可能切换备用模型
            if "overloaded" in name.lower() or "529" in msg or "overloaded" in msg:
                state.consecutive_529 += 1
                if state.consecutive_529 >= MAX_CONSECUTIVE_529:
                    if FALLBACK_MODEL:
                        state.current_model = FALLBACK_MODEL
                        state.consecutive_529 = 0
                        print(f"  \033[31m[529 x{MAX_CONSECUTIVE_529}]"
                              f" 切换到备用模型 {FALLBACK_MODEL}\033[0m")
                    else:
                        state.consecutive_529 = 0
                        print(f"  \033[31m[529 x{MAX_CONSECUTIVE_529}]"
                              f" 未配置 FALLBACK_MODEL_ID，继续重试\033[0m")
                delay = retry_delay(attempt)
                print(f"  \033[33m[529 过载] 重试 {attempt+1}/{MAX_RETRIES},"
                      f" 等待 {delay:.1f}s\033[0m")
                time.sleep(delay)
                continue

            # 非瞬态错误 → 往外抛给外层 try/except
            raise

    raise RuntimeError(f"超过最大重试次数 ({MAX_RETRIES})")


# ── s12: 任务系统 — 文件持久化的任务图 + blockedBy 依赖 ────
# 每个任务是一个 .tasks/{id}.json 文件，有依赖检查、认领、完成解锁。
# s05 的 todo_write 是内存便利贴，s12 是硬盘项目进度图。

@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str          # pending | in_progress | completed
    owner: str | None    # 认领者（多 Agent 场景）
    blockedBy: list[str] # 依赖的任务 ID 列表
    worktree: str | None = None  # s18: 绑定的 worktree 名称


def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def save_task(task: Task):
    _task_path(task.id).write_text(json.dumps(asdict(task), indent=2),
                                   encoding="utf-8")


def load_task(task_id: str) -> Task:
    return Task(**json.loads(_task_path(task_id).read_text(encoding="utf-8")))


def create_task(subject: str, description: str = "",
                blockedBy: list[str] | None = None) -> Task:
    """创建任务并持久化到 .tasks/{id}.json。"""
    task = Task(
        id=f"task_{int(time.time())}_{random.randint(0, 9999):04d}",
        subject=subject,
        description=description,
        status="pending",
        owner=None,
        blockedBy=blockedBy or [],
    )
    save_task(task)
    return task


def list_tasks() -> list[Task]:
    """列出所有任务（读 .tasks/ 下所有 JSON 文件）。"""
    return [Task(**json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(TASKS_DIR.glob("task_*.json"))]


def get_task(task_id: str) -> str:
    """返回单个任务的完整 JSON。"""
    task = load_task(task_id)
    return json.dumps(asdict(task), indent=2, ensure_ascii=False)


def can_start(task_id: str) -> bool:
    """检查 blockedBy 里的所有依赖是否都 completed。
    不存在的依赖视为 blocked。"""
    task = load_task(task_id)
    for dep_id in task.blockedBy:
        if not _task_path(dep_id).exists():
            return False
        if load_task(dep_id).status != "completed":
            return False
    return True


# ── s17: 自治 Agent — 扫描可认领任务 ──────────────────────
def scan_unclaimed_tasks() -> list[dict]:
    """扫描任务板上所有可认领的任务。
    三个条件：pending + 无 owner + 所有 blockedBy 依赖已完成。
    队友在 IDLE 阶段调用此函数来发现可以主动认领的任务。"""
    unclaimed = []
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        task = json.loads(f.read_text(encoding="utf-8"))
        if (task.get("status") == "pending"
                and not task.get("owner")
                and can_start(task["id"])):
            unclaimed.append(task)
    return unclaimed


def claim_task(task_id: str, owner: str = "agent") -> str:
    """认领 pending 任务：设 owner，pending → in_progress。
    依赖未完成或已被认领则拒绝。"""
    task = load_task(task_id)
    if task.status != "pending":
        return f"任务 {task_id} 状态为 {task.status}，无法认领"
    if task.owner:
        return f"任务 {task_id} 已被 {task.owner} 认领"
    if not can_start(task_id):
        deps = [d for d in task.blockedBy
                if not _task_path(d).exists()
                or load_task(d).status != "completed"]
        return f"被阻塞，依赖未完成: {deps}"
    task.owner = owner
    task.status = "in_progress"
    save_task(task)
    print(f"  \033[36m[认领] {task.subject} → in_progress (owner: {owner})\033[0m")
    return f"已认领 {task.id} ({task.subject})"


def complete_task(task_id: str) -> str:
    """完成 in_progress 任务 → completed，并扫描解锁的下游任务。"""
    task = load_task(task_id)
    if task.status != "in_progress":
        return f"任务 {task_id} 状态为 {task.status}，无法完成"
    task.status = "completed"
    save_task(task)
    # 扫描被解锁的下游任务
    unblocked = [t.subject for t in list_tasks()
                 if t.status == "pending" and t.blockedBy
                 and can_start(t.id)]
    print(f"  \033[32m[完成] {task.subject} ✓\033[0m")
    msg = f"已完成 {task.id} ({task.subject})"
    if unblocked:
        msg += f"\n已解锁: {', '.join(unblocked)}"
        print(f"  \033[33m[已解锁] {', '.join(unblocked)}\033[0m")
    return msg


# ── s18: Worktree 隔离系统 — 每个任务独立 git worktree ──────
# 问题: s17 的队友共享同一个工作目录，改同一个文件互相覆盖。
# 解决: git worktree — 同一仓库多个独立工作目录，各干各的。
# 绑定: task.worktree 字段记录绑定关系，不改任务状态（仍 pending 等认领）。
# 安全: name 白名单校验 + 有改动时拒绝删除 + events.jsonl 审计。

def validate_worktree_name(name: str) -> str | None:
    """校验 worktree 名称：只允许字母数字点划线，1-64 字符。拒绝 . 和 .. """
    if not name:
        return "Worktree 名称不能为空"
    if name == "." or name == "..":
        return f"'{name}' 不是合法的 worktree 名称"
    if not VALID_WT_NAME.match(name):
        return (f"非法 worktree 名称 '{name}': "
                "只允许字母、数字、点、下划线、连字符（1-64 字符）")
    return None


def run_git(args: list[str]) -> tuple[bool, str]:
    """执行 git 命令，返回 (成功?, 输出)。"""
    try:
        r = subprocess.run(["git"] + args, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        out = out[:5000] if out else "（无输出）"
        return r.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, "错误: git 超时"


def log_event(event_type: str, worktree_name: str, task_id: str = ""):
    """记录 worktree 生命周期事件到 events.jsonl。"""
    event = {"type": event_type, "worktree": worktree_name,
             "task_id": task_id, "ts": time.time()}
    events_file = WORKTREES_DIR / "events.jsonl"
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def create_worktree(name: str, task_id: str = "") -> str:
    """创建 git worktree + 独立分支。可选绑定到任务。
    绑定不改任务状态，留给队友 IDLE 时自动认领。"""
    err = validate_worktree_name(name)
    if err:
        return f"错误: {err}"
    path = WORKTREES_DIR / name
    if path.exists():
        return f"Worktree '{name}' 已存在于 {path}"
    ok, result = run_git(["worktree", "add", str(path), "-b", f"wt/{name}", "HEAD"])
    if not ok:
        return f"Git 错误: {result}"
    if task_id:
        bind_task_to_worktree(task_id, name)
    log_event("create", name, task_id)
    print(f"  \033[33m[worktree] 创建: {name} @ {path}\033[0m")
    return f"Worktree '{name}' 已创建于 {path}"


def bind_task_to_worktree(task_id: str, worktree_name: str):
    """将任务绑定到 worktree。只写 worktree 字段，任务保持 pending。"""
    task = load_task(task_id)
    task.worktree = worktree_name
    save_task(task)
    print(f"  \033[33m[绑定] {task.subject} → worktree:{worktree_name}\033[0m")


def _count_worktree_changes(path: Path) -> tuple[int, int]:
    """统计 worktree 中未提交文件数和未推送提交数。"""
    try:
        r1 = subprocess.run(["git", "status", "--porcelain"],
                            cwd=path, capture_output=True, text=True, timeout=10)
        files = len([l for l in r1.stdout.strip().splitlines() if l.strip()])
        r2 = subprocess.run(["git", "log", "@{push}..HEAD", "--oneline"],
                            cwd=path, capture_output=True, text=True, timeout=10)
        commits = len([l for l in r2.stdout.strip().splitlines() if l.strip()])
        return files, commits
    except Exception:
        return -1, -1


def remove_worktree(name: str, discard_changes: bool = False) -> str:
    """删除 worktree。有未提交改动时默认拒绝，需 discard_changes=true 强删。"""
    err = validate_worktree_name(name)
    if err:
        return err
    path = WORKTREES_DIR / name
    if not path.exists():
        return f"Worktree '{name}' 未找到"
    if not discard_changes:
        files, commits = _count_worktree_changes(path)
        if files < 0:
            return (f"无法验证 worktree '{name}' 状态。"
                    "使用 discard_changes=true 强制删除。")
        if files > 0 or commits > 0:
            return (f"Worktree '{name}' 有 {files} 个未提交文件 "
                    f"和 {commits} 个未推送提交。"
                    "使用 discard_changes=true 强制删除，"
                    "或 keep_worktree 保留供 review。")
    ok1, _ = run_git(["worktree", "remove", str(path), "--force"])
    if not ok1:
        return f"删除 worktree 目录失败: '{name}'"
    run_git(["branch", "-D", f"wt/{name}"])
    log_event("remove", name)
    print(f"  \033[33m[worktree] 已删除: {name}\033[0m")
    return f"Worktree '{name}' 已删除"


def keep_worktree(name: str) -> str:
    """保留 worktree 分支供人工 review 后合并。"""
    err = validate_worktree_name(name)
    if err:
        return err
    log_event("keep", name)
    print(f"  \033[36m[worktree] 已保留: {name}\033[0m")
    return f"Worktree '{name}' 已保留供 review（分支: wt/{name}）"


# ── s13: 后台任务系统 — 慢操作放后台线程，不阻塞主循环 ──
# 判断：LLM 显式 run_in_background=true 优先，关键词启发式兜底
# 执行：daemon 线程跑，占位符回复 LLM，完成后 <task_notification> 注入

_bg_counter = 0
background_tasks: dict[str, dict] = {}   # bg_id → {tool_use_id, command, status}
background_results: dict[str, str] = {}   # bg_id → output
background_lock = threading.Lock()


def is_slow_operation(tool_name: str, tool_input: dict) -> bool:
    """关键词启发式兜底：命令包含 install/build/test 等视为慢操作。"""
    if tool_name != "bash":
        return False
    cmd = tool_input.get("command", "").lower()
    slow_keywords = ["install", "build", "test", "deploy", "compile",
                     "docker build", "pip install", "npm install",
                     "cargo build", "pytest", "make"]
    return any(kw in cmd for kw in slow_keywords)


def should_run_background(tool_name: str, tool_input: dict) -> bool:
    """LLM 显式请求优先；未指定时用启发式兜底。"""
    if tool_input.get("run_in_background"):
        return True
    return is_slow_operation(tool_name, tool_input)


def start_background_task(block, handlers: dict) -> str:
    """将工具调用包装成 daemon 线程执行，返回 bg_id。
    s20: 接受 handlers 参数（动态工具池），使用 call_tool_handler 安全调用。"""
    global _bg_counter
    _bg_counter += 1
    bg_id = f"bg_{_bg_counter:04d}"
    cmd = block.input.get("command", block.name)

    def worker():
        handler = handlers.get(block.name)
        result = call_tool_handler(handler, block.input, block.name)
        trigger_hooks("PostToolUse", block, result)
        with background_lock:
            background_tasks[bg_id]["status"] = "completed"
            background_results[bg_id] = result

    with background_lock:
        background_tasks[bg_id] = {
            "tool_use_id": block.id,
            "command": cmd,
            "status": "running",
        }
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    print(f"  \033[33m[后台] 已派发 {bg_id}: {cmd[:40]}\033[0m")
    return bg_id


def collect_background_results() -> list[str]:
    """收集已完成的后台任务，格式化为 <task_notification>。"""
    with background_lock:
        ready_ids = [bid for bid, t in background_tasks.items()
                     if t["status"] == "completed"]
    notifications = []
    for bg_id in ready_ids:
        with background_lock:
            task = background_tasks.pop(bg_id)
            output = background_results.pop(bg_id, "")
        summary = output[:200] if len(output) > 200 else output
        notifications.append(
            f"<task_notification>\n"
            f"  <task_id>{bg_id}</task_id>\n"
            f"  <status>completed</status>\n"
            f"  <command>{task['command']}</command>\n"
            f"  <summary>{summary}</summary>\n"
            f"</task_notification>")
        print(f"  \033[32m[后台完成] {bg_id}: "
              f"{task['command'][:40]} ({len(output)} 字符)\033[0m")
    return notifications


# ── s14: Cron 调度系统 — 闹钟线程 + 队列 + 自动交付 ──────
# 四层架构: Scheduler(daemon线程,1s轮询) → Queue(cron_queue) →
#           Queue Processor(agent空闲时拉起) → Consumer(agent_loop注入)
# 生产/交付/消费三者通过 cron_lock + agent_lock 解耦

@dataclass
class CronJob:
    id: str
    cron: str        # 五段式: "分 时 日 月 星期"
    prompt: str      # 触发时注入给 Agent 的消息
    recurring: bool  # True=周期性, False=一次性
    durable: bool    # True=写磁盘(.scheduled_tasks.json)


DURABLE_PATH = WORKDIR / ".scheduled_tasks.json"

scheduled_jobs: dict[str, CronJob] = {}   # job_id → CronJob
cron_queue: list[CronJob] = []            # 调度线程写入, agent_loop 消费
cron_lock = threading.Lock()              # 保护 scheduled_jobs + cron_queue
agent_lock = threading.Lock()             # 防止用户输入和 cron 同时跑 agent_loop
_last_fired: dict[str, str] = {}          # job_id → "YYYY-MM-DD HH:MM"


def _cron_field_matches(field: str, value: int) -> bool:
    """匹配单个 cron 字段：支持 *, */N, N, N-M, N,M,..."""
    if field == "*":
        return True
    if field.startswith("*/"):
        step = int(field[2:])
        return step > 0 and value % step == 0
    if "," in field:
        return any(_cron_field_matches(f.strip(), value)
                   for f in field.split(","))
    if "-" in field:
        lo, hi = field.split("-", 1)
        return int(lo) <= value <= int(hi)
    return value == int(field)


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """检查五段式 cron 表达式是否匹配给定时间。
    标准 cron 语义：DOM 和 DOW 同时约束时任一匹配即可（OR）。"""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    dow_val = (dt.weekday() + 1) % 7  # Python Monday=0 → cron Sunday=0

    m = _cron_field_matches(minute, dt.minute)
    h = _cron_field_matches(hour, dt.hour)
    dom_ok = _cron_field_matches(dom, dt.day)
    month_ok = _cron_field_matches(month, dt.month)
    dow_ok = _cron_field_matches(dow, dow_val)

    if not (m and h and month_ok):
        return False
    dom_unconstrained = dom == "*"
    dow_unconstrained = dow == "*"
    if dom_unconstrained and dow_unconstrained:
        return True
    if dom_unconstrained:
        return dow_ok
    if dow_unconstrained:
        return dom_ok
    return dom_ok or dow_ok


def _validate_cron_field(field: str, lo: int, hi: int) -> str | None:
    """校验单个 cron 字段值在 [lo, hi] 范围内。"""
    if field == "*":
        return None
    if field.startswith("*/"):
        step_str = field[2:]
        if not step_str.isdigit():
            return f"无效步长: {field}"
        if int(step_str) <= 0:
            return f"步长必须 > 0: {field}"
        return None
    if "," in field:
        for part in field.split(","):
            err = _validate_cron_field(part.strip(), lo, hi)
            if err:
                return err
        return None
    if "-" in field:
        parts = field.split("-", 1)
        if not parts[0].isdigit() or not parts[1].isdigit():
            return f"无效范围: {field}"
        a, b = int(parts[0]), int(parts[1])
        if a < lo or a > hi or b < lo or b > hi:
            return f"范围 {field} 超出 [{lo}-{hi}]"
        if a > b:
            return f"范围起点 > 终点: {field}"
        return None
    if not field.isdigit():
        return f"无效字段: {field}"
    val = int(field)
    if val < lo or val > hi:
        return f"值 {val} 超出 [{lo}-{hi}]"
    return None


def validate_cron(cron_expr: str) -> str | None:
    """校验整条 cron 表达式。返回错误消息或 None。"""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return f"需要 5 个字段，实际 {len(fields)} 个"
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    names = ["分钟", "小时", "日", "月", "星期"]
    for i, (field, (lo, hi), name) in enumerate(zip(fields, bounds, names)):
        err = _validate_cron_field(field, lo, hi)
        if err:
            return f"{name}: {err}"
    return None


def save_durable_jobs():
    """持久化 durable 任务到 .scheduled_tasks.json。"""
    with cron_lock:
        durable = [asdict(j) for j in scheduled_jobs.values() if j.durable]
    DURABLE_PATH.write_text(json.dumps(durable, indent=2, ensure_ascii=False),
                            encoding="utf-8")


def load_durable_jobs():
    """启动时从磁盘恢复 durable 任务。跳过非法 cron 表达式。"""
    if not DURABLE_PATH.exists():
        return
    try:
        jobs = json.loads(DURABLE_PATH.read_text(encoding="utf-8"))
        for j in jobs:
            job = CronJob(**j)
            err = validate_cron(job.cron)
            if err:
                print(f"  \033[31m[cron] 跳过非法任务 {job.id}: {err}\033[0m")
                continue
            scheduled_jobs[job.id] = job
        valid = [j for j in jobs if j["id"] in scheduled_jobs]
        if valid:
            print(f"  \033[35m[cron] 已加载 {len(valid)} 个 durable 任务\033[0m")
    except Exception:
        pass


def schedule_job(cron: str, prompt: str, recurring: bool = True,
                 durable: bool = True) -> CronJob | str:
    """注册新的 cron 任务。先校验，再入 scheduled_jobs，durable 则写磁盘。"""
    err = validate_cron(cron)
    if err:
        return err
    job = CronJob(
        id=f"cron_{random.randint(0, 999999):06d}",
        cron=cron, prompt=prompt,
        recurring=recurring, durable=durable,
    )
    with cron_lock:
        scheduled_jobs[job.id] = job
    if durable:
        save_durable_jobs()
    print(f"  \033[35m[cron 注册] {job.id} '{cron}' → {prompt[:40]}\033[0m")
    return job


def cancel_job(job_id: str) -> str:
    """取消 cron 任务。durable 则更新磁盘。"""
    with cron_lock:
        job = scheduled_jobs.pop(job_id, None)
    if not job:
        return f"未找到任务 {job_id}"
    if job.durable:
        save_durable_jobs()
    print(f"  \033[31m[cron 取消] {job_id}\033[0m")
    return f"已取消 {job_id}"


def cron_scheduler_loop():
    """独立 daemon 线程：每秒轮询，时间匹配的 job 塞进 cron_queue。
    单个 job 异常不影响整个调度线程。"""
    while True:
        time.sleep(1)
        now = datetime.now()
        minute_marker = now.strftime("%Y-%m-%d %H:%M")  # 日期感知，防止跨天跳过
        with cron_lock:
            for job in list(scheduled_jobs.values()):
                try:
                    if cron_matches(job.cron, now):
                        if _last_fired.get(job.id) != minute_marker:
                            cron_queue.append(job)
                            _last_fired[job.id] = minute_marker
                            print(f"  \033[35m[cron 触发] {job.id} → "
                                  f"{job.prompt[:40]}\033[0m")
                        if not job.recurring:
                            scheduled_jobs.pop(job.id, None)
                            if job.durable:
                                save_durable_jobs()
                except Exception as e:
                    print(f"  \033[31m[cron 错误] {job.id}: {e}\033[0m")


def consume_cron_queue() -> list[CronJob]:
    """消费 cron_queue 中已触发的任务（agent_loop 调用）。"""
    with cron_lock:
        fired = list(cron_queue)
        cron_queue.clear()
    return fired


def has_cron_queue() -> bool:
    """检查是否有待交付的 cron 任务。"""
    with cron_lock:
        return bool(cron_queue)


# ── s15: Agent Teams — MessageBus + 队友线程 ──────────────
# 多 Agent 通过文件收件箱（.mailboxes/*.jsonl）通信。
# Lead 用 spawn_teammate 招队友，队友在独立 daemon 线程里干活，
# 完成后发消息到 Lead 收件箱，主循环注入 [收件箱] 到对话。
# s06 的 task 是临时工（即用即抛），s15 的 teammate 是队员（可通信、并行）。

MAILBOX_DIR = WORKDIR / ".mailboxes"
MAILBOX_DIR.mkdir(exist_ok=True)


class MessageBus:
    """文件收件箱：发消息 = append JSONL 行，读消息 = 读+删（消费式）。
    教学版无文件锁；真实 CC 用 proper-lockfile。"""

    def send(self, from_agent: str, to_agent: str, content: str,
             msg_type: str = "message", metadata: dict = None):
        msg = {"from": from_agent, "to": to_agent,
               "content": content, "type": msg_type,
               "ts": time.time(), "metadata": metadata or {}}
        inbox = MAILBOX_DIR / f"{to_agent}.jsonl"
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        print(f"  \033[33m[消息总线] {from_agent} → {to_agent}: "
              f"{content[:50]}\033[0m")

    def read_inbox(self, agent: str) -> list[dict]:
        """读取并清空收件箱（消费式）。"""
        inbox = MAILBOX_DIR / f"{agent}.jsonl"
        if not inbox.exists():
            return []
        msgs = [json.loads(line) for line in inbox.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        inbox.unlink()
        return msgs


BUS = MessageBus()
active_teammates: dict[str, bool] = {}

# ── s16: 协议系统 — 结构化请求-响应 + request_id 追踪 ────
# s15 的队友通信是松散的文本消息。s16 加了工单系统：
# 每个请求带唯一 request_id，回复带同一个 request_id 回来，
# ProtocolState 追踪状态（pending→approved/rejected），
# match_response 按 ID 关联 + 类型校验，防止关机回复误批计划。

@dataclass
class ProtocolState:
    request_id: str       # "req_004281" — 贯穿全链路的唯一编号
    type: str             # "shutdown" | "plan_approval"
    sender: str           # 发起方
    target: str           # 接收方
    status: str           # pending | approved | rejected
    payload: str          # 计划文本或关机原因
    created_at: float = field(default_factory=time.time)


pending_requests: dict[str, ProtocolState] = {}


def new_request_id() -> str:
    return f"req_{random.randint(0, 999999):06d}"


def match_response(response_type: str, request_id: str, approve: bool):
    """按 request_id 将回复关联到原请求。
    校验响应类型与请求类型匹配，防止跨类型误匹配。
    已处理的请求忽略重复回复。"""
    state = pending_requests.get(request_id)
    if not state:
        print(f"  \033[31m[协议] 未知 request_id: {request_id}\033[0m")
        return
    if state.type == "shutdown" and response_type != "shutdown_response":
        print(f"  \033[31m[协议] 类型不匹配: 期望 shutdown_response,"
              f" 收到 {response_type}\033[0m")
        return
    if state.type == "plan_approval" and response_type != "plan_approval_response":
        print(f"  \033[31m[协议] 类型不匹配: 期望 plan_approval_response,"
              f" 收到 {response_type}\033[0m")
        return
    if state.status != "pending":
        print(f"  \033[33m[协议] {request_id} 已 {state.status}，忽略重复\033[0m")
        return
    state.status = "approved" if approve else "rejected"
    icon = "✓" if approve else "✗"
    color = "32" if approve else "31"
    print(f"  \033[{color}m[协议] {state.type} {icon} "
          f"({request_id}: {state.status})\033[0m")


def consume_lead_inbox(route_protocol: bool = True) -> list[dict]:
    """统一收件箱消费：先路由协议回复（match_response），再返回全部消息。
    run_check_inbox 和 _inject_inbox 都走这个入口，
    避免消息被读取但协议状态未更新的问题。"""
    msgs = BUS.read_inbox("lead")
    if not msgs:
        return []
    if route_protocol:
        for msg in msgs:
            meta = msg.get("metadata", {})
            req_id = meta.get("request_id", "")
            msg_type = msg.get("type", "")
            if req_id and msg_type.endswith("_response"):
                match_response(msg_type, req_id, meta.get("approve", False))
    return msgs


# ── s17: 自治 Agent — 空闲轮询 + 自动认领 ──────────────────
# s16 的 idle loop 只是 while+sleep 等消息。
# s17 升级为结构化轮询：每 5 秒检查 inbox（优先）→ 扫描任务板 →
# 自动认领 → 回到 WORK。60 秒无事可做则超时关机。

IDLE_POLL_INTERVAL = 5   # 空闲轮询间隔（秒）
IDLE_TIMEOUT = 60         # 空闲超时（秒）


def idle_poll(agent_name: str, messages: list,
              name: str, role: str,
              worktree_context: dict | None = None) -> str:
    """空闲轮询 60 秒（每 5 秒一次）。
    返回 'work'（有新任务或消息）、'shutdown'（收到关机请求）、
    或 'timeout'（60 秒无事可做）。

    优先级：inbox 协议消息 > inbox 普通消息 > 任务板自动认领。

    关机请求在 IDLE 阶段直接处理并回复，不等到下一轮 WORK——
    这样即使队友在 IDLE，Lead 的 shutdown_request 也能在 5 秒内得到响应。"""
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
                    print(f"  \033[35m[协议] {name} 在 IDLE 中同意关机 "
                          f"({req_id})\033[0m")
                    return "shutdown"

            # 普通消息 → 注入上下文，回到 WORK
            messages.append({"role": "user",
                "content": "<inbox>" + json.dumps(inbox, ensure_ascii=False) + "</inbox>"})
            print(f"  \033[36m[空闲] {name} 发现收件箱消息\033[0m")
            return "work"

        # ② 扫描任务板
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
                print(f"  \033[32m[空闲] {name} 自动认领: "
                      f"{task['subject']}\033[0m")
                return "work"
            print(f"  \033[33m[空闲] {name} 认领失败: "
                  f"{result}\033[0m")

    print(f"  \033[31m[空闲] {name} 超时 ({IDLE_TIMEOUT}s)，将关机\033[0m")
    return "timeout"


# ── Teammate 线程 — s17: WORK→IDLE→SHUTDOWN 三阶段生命周期 ──

def spawn_teammate_thread(name: str, role: str, prompt: str) -> str:
    """在后台 daemon 线程里启动自治队友 Agent。
    s17: WORK→IDLE→SHUTDOWN 三阶段生命周期。
    队友可自行扫描任务板、认领任务、完成任务，不需要 Lead 手动分配。
    工具集: bash/read_file/write_file/send_message/submit_plan/list_tasks/claim_task/complete_task。"""
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
            print(f"  \033[35m[协议] {name} 同意关机 ({req_id})\033[0m")
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
        }

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
                except Exception:
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
            idle_result = idle_poll(name, messages, name, role, wt_ctx)
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
        print(f"  \033[32m[队友] {name} 已关机\033[0m")

    active_teammates[name] = True
    threading.Thread(target=run, daemon=True).start()
    print(f"  \033[36m[队友] {name} 已启动，角色: {role}（自治模式）\033[0m")
    return f"队友 '{name}' 已启动，角色: {role}（自治模式，可自行认领任务）"


# ── s04: 钩子系统 — 把扩展逻辑从循环中移出来 ──────────────
# 挂在循环上的函数，用一个函数打包挂载
HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

def register_hook(event: str, callback):
    """注册钩子：把回调函数绑定到指定事件上"""
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    """触发钩子：依次调用该事件的所有回调。任一返回非 None 就阻断后续。"""
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


# ── 钩子函数定义 ─────────────────────────────────────────
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]

def permission_hook(block):
    """PreToolUse: 三级权限检查 — 拒绝列表 → 危险操作 → 用户确认"""
    if block.name == "bash":
        for pattern in DENY_LIST:
            if pattern in block.input.get("command", ""):
                print(f"\n\033[31m⛔ 已阻止: '{pattern}'\033[0m")
                return "权限拒绝: 命中拒绝列表"
        for kw in DESTRUCTIVE:
            if kw in block.input.get("command", ""):
                print(f"\n\033[33m⚠  潜在危险命令\033[0m")
                print(f"   工具: {block.name}({block.input})")
                choice = input("   允许执行? [y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "权限拒绝: 用户不同意"
    if block.name in ("write_file", "edit_file"):
        path = block.input.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            print(f"\n\033[33m⚠  写入工作目录之外\033[0m")
            print(f"   工具: {block.name}({block.input})")
            choice = input("   允许写入? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限拒绝: 用户不同意"
    # s20: MCP 外部工具的权限检查 — 部署类工具需用户确认
    if block.name.startswith("mcp__") and "deploy" in block.name:
        print(f"\n\033[33m[权限] MCP 部署类工具: {block.name}\033[0m")
        choice = input("   允许执行? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "权限拒绝: 用户不同意"
    return None

def log_hook(block):
    """PreToolUse: 记录每次工具调用"""
    args_preview = str(list(block.input.values())[:2])[:60]
    print(f"\033[90m[钩子] {block.name}({args_preview})\033[0m")
    return None

def large_output_hook(block, output):
    """PostToolUse: 输出过大时发出警告"""
    if len(str(output)) > 100000:
        print(f"\033[33m[钩子] ⚠ {block.name} 输出过大: {len(str(output))} 字符\033[0m")
    return None

def context_inject_hook(query: str):
    """UserPromptSubmit: 用户输入前记录工作目录"""
    print(f"\033[90m[钩子] 用户输入: 工作目录 {WORKDIR}\033[0m")
    return None

def summary_hook(messages: list):
    """Stop: 会话结束时打印工具调用统计"""
    tool_count = sum(1 for m in messages
                     for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    print(f"\033[90m[钩子] 会话结束: 共调用 {tool_count} 次工具\033[0m")
    return None

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


# ── 核心模式: 注入记忆 → 压缩 → 问模型 → 执行工具 → 提取记忆 ──
# s09: 在 s08 压缩管线的基础上，每轮注入相关记忆、结束提取新记忆。
# 流程:
# ── s20: agent_loop 辅助函数 — 把循环中的重复逻辑提取为独立函数 ──
rounds_since_todo = 0  # s05: 记录连续多少轮没有更新 todo


def prepare_context(messages: list) -> list:
    """LLM 调用前的上下文准备管线：L3→L1→L2→阈值?→L4"""
    messages[:] = tool_result_budget(messages)    # L3: 大结果落盘
    messages[:] = snip_compact(messages)          # L1: 裁剪中间消息
    messages[:] = micro_compact(messages)         # L2: 旧结果占位
    if estimate_size(messages) > CONTEXT_LIMIT:
        print("[自动压缩]")
        messages[:] = compact_history(messages)   # L4: LLM 摘要
    return messages


def build_user_content(results: list[dict]) -> list[dict]:
    """合并工具结果和后台通知为用户消息内容。"""
    content = list(results)
    for note in collect_background_results():
        content.append({"type": "text", "text": note})
    return content


def inject_background_notifications(messages: list):
    """将已完成的后台任务通知注入 messages。"""
    notes = collect_background_results()
    if notes:
        messages.append({"role": "user", "content": [
            {"type": "text", "text": note} for note in notes]})


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
    """智能体循环: 注入记忆 → 压缩 → 执行 → 提取记忆。
    s20: 使用 prepare_context/build_user_content/call_llm 提取的公共函数。"""
    global rounds_since_todo
    tools, handlers = assemble_tool_pool()
    state = RecoveryState()
    max_tokens = DEFAULT_MAX_TOKENS

    # s09: 加载记忆 + 找注入位置
    memories_content = load_memories(messages)
    memory_turn = None
    for i in range(len(messages) - 1, -1, -1):
        if (messages[i].get("role") == "user"
                and isinstance(messages[i].get("content"), str)):
            memory_turn = i
            break

    while True:
        # s14: 注入已触发的 cron 任务
        fired = consume_cron_queue()
        for job in fired:
            messages.append({"role": "user",
                             "content": f"[定时任务] {job.prompt}"})

        # s13: 注入已完成的后台任务通知
        inject_background_notifications(messages)

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

        # s09: 记忆拼接到当前用户消息前面
        request_messages = messages
        if memories_content and memory_turn is not None and memory_turn < len(messages):
            request_messages = messages.copy()
            request_messages[memory_turn] = {
                **messages[memory_turn],
                "content": memories_content + "\n\n" + messages[memory_turn]["content"],
            }

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
            print(f"\033[36m> {block.name}\033[0m")

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


# ── 入口: 交互式对话 ───────────────────────────────────
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
        if query.strip().lower() in ("q", "exit", ""):
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
