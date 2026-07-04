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
import os, re
from pathlib import Path
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
# 用 __file__ 定位脚本所在目录，不受终端当前工作目录影响
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# 如果设置了自定义 BASE_URL (比如用中转平台或 DeepSeek),
# 就清除 ANTHROPIC_AUTH_TOKEN, 避免认证冲突
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
WORKDIR = Path.cwd()
RUNTIME_DIR = WORKDIR / ".runtime"           # 所有运行时产物统一存放
RUNTIME_DIR.mkdir(exist_ok=True)
SKILLS_DIR = WORKDIR / "skills"
TRANSCRIPT_DIR = RUNTIME_DIR / "transcripts"
TOOL_RESULTS_DIR = RUNTIME_DIR / "tool-results"
MEMORY_DIR = RUNTIME_DIR / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
TASKS_DIR = RUNTIME_DIR / "tasks"
TASKS_DIR.mkdir(exist_ok=True)
WORKTREES_DIR = RUNTIME_DIR / "worktrees"
WORKTREES_DIR.mkdir(exist_ok=True)
VALID_WT_NAME = re.compile(r'^[A-Za-z0-9._-]{1,64}$')  # s18: worktree 名称校验
CURRENT_TODOS: list[dict] = []           # s05: 内存中的任务列表
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
PRIMARY_MODEL = os.environ["MODEL_ID"]
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL_ID")

def safe_print(*args, **kwargs):
    """安全打印：Windows GBK 终端下自动替换不可编码字符。"""
    import sys
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or 'ascii'
        safe_args = [str(a).encode(enc, errors='replace').decode(enc) for a in args]
        print(*safe_args, **kwargs)
