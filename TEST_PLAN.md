# mes1 项目测试规划提示词

你需要为 `d:\Agent\0-1claude` 下的 mes1 项目（一个 AI 编程智能体）编写并执行**完整的测试套件**。

---

## 项目结构速览

```
0-1claude/
├── app.py                  # 主入口（交互式循环）
├── config.py               # 全局配置、imports、路径常量
├── core/
│   ├── utils.py            # 通用工具函数（safe_path, run_bash, has_tool_use 等）
│   ├── prompt.py           # System Prompt 组装/缓存
│   ├── compression.py      # 四层上下文压缩
│   ├── recovery.py         # 错误恢复（指数退避、模型切换）
│   └── engine.py           # agent_loop 核心循环
├── services/
│   ├── skills.py           # 技能扫描/加载
│   ├── memory.py           # 记忆读写/检索/整理
│   ├── tasks.py            # 任务图 CRUD + 依赖管理
│   ├── cron.py             # Cron 调度（解析/匹配/持久化）
│   └── background.py       # 后台任务线程
├── tools/
│   ├── builtin.py          # 工具定义 + handler 映射
│   ├── subagent.py         # 子 Agent 派发
│   ├── team.py             # 团队/worktree/MCP handler
│   └── mcp.py              # MCP 插件系统
└── runtime/
    ├── hooks.py            # 钩子系统 + 权限检查
    ├── bus.py              # MessageBus 文件收件箱
    ├── protocol.py         # 协议状态机
    ├── teammate.py         # 队友自治循环
    └── worktree.py         # git worktree 隔离
```

---

## 一、测试原则

1. **不用 mock 测试有外部依赖的函数**——API 调用、git 操作、用户输入用 mock
2. **纯函数直接测**——输入输出确定，无副作用
3. **文件 I/O 用临时目录**——每个测试在 `tempfile.TemporaryDirectory` 内运行
4. **每个模块写一个对应的 test 文件**——放在 `tests/` 目录
5. **中文注释保留不删**
6. **只测我们自己的代码**——不测试 anthropic SDK 或 stdlib

---

## 二、测试环境搭建

### 2.1 安装依赖

```bash
pip install pytest pytest-mock
```

### 2.2 创建 tests 目录

```
0-1claude/
└── tests/
    ├── __init__.py              # 空
    ├── conftest.py              # 共享 fixtures
    ├── test_config.py           # config.py
    ├── test_utils.py            # core/utils.py
    ├── test_prompt.py           # core/prompt.py
    ├── test_compression.py      # core/compression.py
    ├── test_recovery.py         # core/recovery.py
    ├── test_skills.py           # services/skills.py
    ├── test_memory.py           # services/memory.py
    ├── test_tasks.py            # services/tasks.py
    ├── test_cron.py             # services/cron.py
    ├── test_background.py       # services/background.py
    ├── test_mcp.py              # tools/mcp.py
    ├── test_bus.py              # runtime/bus.py
    ├── test_protocol.py         # runtime/protocol.py
    ├── test_hooks.py            # runtime/hooks.py
    ├── test_worktree.py         # runtime/worktree.py
    └── test_integration.py      # 集成测试
```

### 2.3 conftest.py 内容

```python
"""共享 fixtures：mock Anthropic client + 临时工作目录"""
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def temp_workdir(monkeypatch):
    """用临时目录替代所有运行时路径，隔离文件 I/O 副作用。"""
    with tempfile.TemporaryDirectory() as tmp:
        rt = Path(tmp) / ".runtime"
        rt.mkdir()
        (rt / "tasks").mkdir()
        (rt / "mailboxes").mkdir()
        (rt / "worktrees").mkdir()

        # config.py 全局路径
        monkeypatch.setattr("config.WORKDIR", Path(tmp))
        monkeypatch.setattr("config.RUNTIME_DIR", rt)
        monkeypatch.setattr("config.TASKS_DIR", rt / "tasks")
        monkeypatch.setattr("config.MEMORY_DIR", rt / "memory")
        monkeypatch.setattr("config.MEMORY_INDEX", rt / "memory" / "MEMORY.md")
        monkeypatch.setattr("config.TRANSCRIPT_DIR", rt / "transcripts")
        monkeypatch.setattr("config.TOOL_RESULTS_DIR", rt / "tool-results")
        monkeypatch.setattr("config.WORKTREES_DIR", rt / "worktrees")
        monkeypatch.setattr("config.SKILLS_DIR", Path(tmp) / "skills")

        # 跨模块常量
        monkeypatch.setattr("runtime.bus.MAILBOX_DIR", rt / "mailboxes")
        monkeypatch.setattr("services.cron.DURABLE_PATH", rt / "scheduled_tasks.json")

        yield Path(tmp)


@pytest.fixture
def make_mock_response():
    """工厂函数：生成指定内容的 mock Anthropic 响应。"""

    class FakeBlock:
        def __init__(self, btype, **kw):
            self.type = btype
            for k, v in kw.items():
                setattr(self, k, v)

    class FakeResponse:
        def __init__(self, blocks, stop_reason="end_turn"):
            self.content = blocks
            self.stop_reason = stop_reason

    def _make(blocks=None, stop_reason="end_turn"):
        return FakeResponse(
            blocks or [FakeBlock("text", text="mock response")],
            stop_reason,
        )

    return _make


@pytest.fixture
def mock_client(monkeypatch, make_mock_response):
    """Mock anthropic client.messages.create。"""
    fake = type("FakeClient", (), {
        "messages": type("FakeMessages", (), {
            "create": lambda *a, **kw: make_mock_response()
        })()
    })
    monkeypatch.setattr("config.client", fake)
    return fake


@pytest.fixture(autouse=True)
def mock_lazy_imports(monkeypatch):
    """预设延迟导入的模块，避免测试中 NameError。"""
    monkeypatch.setattr("tools.builtin.BUILTIN_HANDLERS", {"bash": lambda: None}, raising=False)
    monkeypatch.setattr("tools.builtin.SUB_HANDLERS", {"bash": lambda: None}, raising=False)
    monkeypatch.setattr("tools.mcp.mcp_clients", {}, raising=False)
```

---

## 三、每个测试文件的测试要点

### 3.1 `test_config.py` — 全局配置（~20 个测试）

**测试内容：**

| 测试点 | 方法 |
|--------|------|
| `WORKDIR` 存在且为 Path 对象 | 直接 import 检查 |
| `PRIMARY_MODEL` 从环境变量正确读取 | `monkeypatch.setenv("MODEL_ID", "test-model")` 后重新 import |
| `FALLBACK_MODEL` 未设置时返回 None | `monkeypatch.delenv("FALLBACK_MODEL_ID", raising=False)` |
| `READLINE_AVAILABLE` 为 bool | 直接检查 |
| `CURRENT_TODOS` 初始为空列表 | 直接检查 |
| `client` 已实例化 | 检查 `isinstance(client, Anthropic)` |
| `.env` 加载不影响默认行为 | 确保无 .env 文件时也不崩溃 |

**不需要测的：** anthropic SDK 的初始化细节

---

### 3.2 `test_utils.py` — 核心工具函数（~35 个测试）

**这是最重要的测试文件——纯函数多，不依赖外部 API。**

| 函数 | 测试点 |
|------|--------|
| `safe_path()` | ✅ 正常路径解析；✅ WORKDIR 内路径；✅ 路径越界抛异常；✅ 符号链接攻击；✅ `..` 穿透攻击；✅ cwd 参数行为 |
| `extract_text()` | ✅ 字符串直传；✅ list[Block] 提取；✅ 空列表；✅ 混合 text + tool_use 块 |
| `has_tool_use()` | ✅ 含 tool_use 块的 content；✅ 纯文本 content；✅ 空 content |
| `call_tool_handler()` | ✅ handler 存在且参数正确；✅ handler 不存在返回错误；✅ 参数不匹配返回 TypeError 提示；✅ handler 返回空字符串 |
| `estimate_size()` | ✅ 空列表；✅ 单条消息；✅ 多条消息 |
| `_block_type()` | ✅ dict 格式；✅ 对象格式；✅ 无 type 字段返回 None |
| `_message_has_tool_use()` | ✅ assistant + tool_use；✅ assistant + 纯 text；✅ user role；✅ 非列表 content |
| `_is_tool_result_message()` | ✅ user + tool_result；✅ assistant role；✅ 非列表 content |
| `terminal_print()` | ✅ 主线程 print；✅ 后台线程（用 mock readline） |
| `run_bash()` | ✅ 简单命令（echo）；✅ 输出截断（>50000 字符）；✅ 超时；✅ 错误命令 |
| `run_read()` | ✅ 正常文件；✅ 文件不存在；✅ limit 截断；✅ 路径越界 |
| `run_write()` | ✅ 正常写入；✅ 父目录自动创建；✅ 路径越界 |
| `run_edit()` | ✅ 正常替换；✅ old_text 不存在；✅ 路径越界 |
| `run_find()` | ✅ 匹配文件；✅ 无匹配；✅ 危险 pattern 不越界 |
| `_normalize_todos()` | ✅ 正常列表；✅ JSON 字符串；✅ 无效格式；✅ 缺少字段；✅ 无效 status |
| `run_todo_write()` | ✅ 正常更新；✅ 更新 CURRENT_TODOS；✅ 无效输入返回错误 |

---

### 3.3 `test_prompt.py` — System Prompt 组装（~10 个测试）

| 测试点 | 方法 |
|--------|------|
| `PROMPT_SECTIONS` 包含必需 key | 检查 identity/memory_instruction/skills_instruction/mcp_instruction |
| `assemble_system_prompt()` 基础输出 | mock context（无技能/无记忆/无 MCP） |
| `assemble_system_prompt()` 含技能目录 | context 中有 skills_catalog |
| `assemble_system_prompt()` 含记忆 | context 中有 memories |
| `assemble_system_prompt()` 含 MCP server | mock `mcp_clients` 为非空 |
| `get_system_prompt()` 缓存命中 | 相同 context 返回相同结果 |
| `update_context()` 返回必要字段 | 检查 enabled_tools/workspace/memories/skills_catalog/mcp_servers |
| `SUB_SYSTEM` 非空 | 直接检查 |

**mock 技巧**：`update_context` 内引用了 `BUILTIN_HANDLERS`, `list_skills()`, `read_memory_index()`, `mcp_clients`——测试时用 `monkeypatch` 替换这些值。

---

### 3.4 `test_compression.py` — 上下文压缩（~25 个测试）

**核心测试——压缩管线是 agent 循环的关键机制。**

| 函数 | 测试点 |
|------|--------|
| `collect_tool_results()` | ✅ 有 tool_result；✅ 无 tool_result；✅ 多个消息混合；✅ 返回位置三元组 |
| `snip_compact()` | ✅ 消息数 < 上限不变；✅ 超上限裁剪中间；✅ 不拆散 tool_use+tool_result 对；✅ 保留头尾 |
| `micro_compact()` | ✅ 工具结果少时不变；✅ 多工具结果时旧结果被占位符替换；✅ 占位符内容正确 |
| `persist_large_output()` | ✅ 文件创建 + 内容正确；✅ 返回预览格式正确 |
| `tool_result_budget()` | ✅ 不超标不变；✅ 超标时最大结果先落盘；✅ 落盘后总量在预算内 |
| `write_transcript()` | ✅ 文件创建 + JSONL 格式正确 |
| `compact_history()` | ✅ 调用 summarize；✅ 返回压缩后的消息列表 |
| `reactive_compact()` | ✅ 比 compact_history 更激进；✅ 保留尾部消息 |

**注意**：`summarize_history()` 内部调用 `client.messages.create()`——测试时用 mock 返回假摘要。

---

### 3.5 `test_recovery.py` — 错误恢复（~15 个测试）

| 函数 | 测试点 |
|------|--------|
| `RecoveryState` | ✅ 初始值正确；✅ 字段可修改 |
| `retry_delay()` | ✅ 第 0 次 ~0.5s；✅ 第 5 次 ~16s；✅ 上限 32s；✅ Retry-After 优先 |
| `is_prompt_too_long_error()` | ✅ 匹配 "prompt is too long"；✅ 匹配 "prompt_is_too_long"；✅ 匹配 "context_length_exceeded"；✅ 不匹配普通错误 |
| `with_retry()` | ✅ 成功时直接返回；✅ 429 后重试并成功；✅ 529 后重试；✅ 连续 529 切换模型；✅ 非瞬态错误直接抛；✅ 超最大重试抛 RuntimeError |

**mock 技巧**：`with_retry(fn, state)` — 传入一个 mock `fn`，前几次抛 429/529 异常，最后一次返回成功值。

---

### 3.6 `test_skills.py` — 技能系统（~10 个测试）

| 测试点 | 方法 |
|--------|------|
| `_parse_frontmatter()` YAML 头 | ✅ 正常解析；✅ 无 frontmatter 返回空 dict；✅ 格式错误不崩溃 |
| `_scan_skills()` 扫描空目录 | 临时目录下无 skills/，不崩溃 |
| `_scan_skills()` 扫描含 SKILL.md 的目录 | 创建临时 skills/test-skill/SKILL.md 后验证 SKILL_REGISTRY |
| `list_skills()` 空注册表 | 返回"未找到技能" |
| `list_skills()` 含技能 | 返回正确的名称+描述 |
| `load_skill()` 存在 | 返回完整内容 |
| `load_skill()` 不存在 | 返回错误提示 |

**fixture 技巧**：monkeypatch `SKILLS_DIR` 指向临时目录，在临时目录中创建 `skills/test-skill/SKILL.md`。

---

### 3.7 `test_memory.py` — 记忆系统（~25 个测试）

| 函数 | 测试点 |
|------|--------|
| `_parse_memory_frontmatter()` | ✅ 正常解析 name/description/type；✅ 无 frontmatter；✅ body 正确提取 |
| `write_memory_file()` | ✅ 文件创建；✅ YAML frontmatter 格式；✅ 自动调用 _rebuild_index |
| `_rebuild_index()` | ✅ 空目录；✅ 含记忆文件；✅ 跳过 MEMORY.md |
| `read_memory_index()` | ✅ 有索引；✅ MEMORY.md 不存在 |
| `read_memory_file()` | ✅ 文件存在；✅ 文件不存在 |
| `list_memory_files()` | ✅ 空目录；✅ 含文件；✅ 跳过 MEMORY.md |
| `select_relevant_memories()` | ✅ 空文件列表；✅ LLM 正常返回（mock）；✅ LLM 异常走关键词降级 |
| `load_memories()` | ✅ 无相关记忆返回空；✅ 有相关记忆返回标签包裹内容 |
| `extract_memories()` | ✅ 成功提取新记忆（mock）；✅ 已有记忆覆盖时跳过；✅ 无新内容返回 |
| `consolidate_memories()` | ✅ 文件数未达阈值不触发；✅ 达阈值后整理 |

---

### 3.8 `test_tasks.py` — 任务系统（~25 个测试）

**纯文件 I/O，无外部依赖——最好测的模块之一。**

| 函数 | 测试点 |
|------|--------|
| `Task` dataclass | ✅ 默认值；✅ 字段类型 |
| `create_task()` | ✅ 正常创建 + 文件持久化；✅ 含 description；✅ 含 blockedBy |
| `list_tasks()` | ✅ 空目录；✅ 含多个任务；✅ 返回 Task 对象 |
| `get_task()` | ✅ 存在返回 JSON；✅ 不存在抛异常 |
| `load_task()` | ✅ 正常加载；✅ 文件不存在抛异常 |
| `save_task()` | ✅ 持久化后可 load 出来 |
| `can_start()` | ✅ 无依赖；✅ 依赖已完成；✅ 依赖未完成；✅ 依赖不存在 |
| `scan_unclaimed_tasks()` | ✅ 空目录；✅ pending+无owner+可开始 → 返回；✅ 已被认领的跳过；✅ 被阻塞的跳过 |
| `claim_task()` | ✅ 正常认领 pending→in_progress；✅ 非 pending 拒绝；✅ 已被认领拒绝；✅ 被阻塞拒绝 |
| `complete_task()` | ✅ 正常完成 in_progress→completed；✅ 非 in_progress 拒绝；✅ 解锁下游任务 |
| `run_*` handler 函数 | ✅ 各 handler 调用对应核心函数 |

---

### 3.9 `test_cron.py` — Cron 调度（~30 个测试）

**大量纯函数，非常适合单元测试。**

| 函数 | 测试点 |
|------|--------|
| `_cron_field_matches()` | ✅ `*` 匹配所有；✅ `*/N` 步进；✅ 精确值匹配/不匹配；✅ 范围 `N-M`；✅ 逗号列表；✅ 负数步进拒绝 |
| `cron_matches()` | ✅ 匹配整点；✅ `0 9 * * *` 每天 9 点；✅ `0 9 * * 1-5` 工作日 9 点；✅ DOM 和 DOW 同时约束（OR 语义）；✅ 分钟不匹配 |
| `_validate_cron_field()` | ✅ 合法值；✅ 超出范围；✅ `*/N` 步进；✅ 非法字符 |
| `validate_cron()` | ✅ 合法表达式；✅ 字段数不对；✅ 范围越界；✅ 每个字段错误定位 |
| `schedule_job()` | ✅ 合法 cron 正常调度；✅ 非法 cron 返回错误；✅ durable 写磁盘 |
| `cancel_job()` | ✅ 存在取消；✅ 不存在返回错误；✅ durable 更新磁盘 |
| `save_durable_jobs()` / `load_durable_jobs()` | ✅ 保存后加载一致；✅ 空任务列表；✅ 非法 cron 加载时跳过 |
| `consume_cron_queue()` | ✅ 空队列；✅ 消费后清空 |
| `has_cron_queue()` | ✅ 空；✅ 非空 |

**不需要测的：** `cron_scheduler_loop()`（无限循环 daemon 线程，不适合单元测试）

---

### 3.10 `test_background.py` — 后台任务（~10 个测试）

| 函数 | 测试点 |
|------|--------|
| `is_slow_operation()` | ✅ 非 bash 工具返回 False；✅ 含 "install" 返回 True；✅ 含 "build"/"test"/"deploy"；✅ 不含关键词返回 False |
| `should_run_background()` | ✅ run_in_background=True 优先；✅ 未设置走启发式 |

**不需要测的**：`start_background_task()`（涉及 threading + API mock）、`collect_background_results()`（纯字典操作但依赖 start 的副作用）

---

### 3.11 `test_mcp.py` — MCP 插件（~15 个测试）

| 函数/类 | 测试点 |
|---------|--------|
| `MCPClient` | ✅ 实例化；✅ register 后 tools 和 handlers 可访问；✅ call_tool 调用正确 handler；✅ call_tool 未知工具返回错误；✅ handler 异常不崩溃 |
| `normalize_mcp_name()` | ✅ 合法名称不变；✅ 含空格替换为 `_`；✅ 含特殊字符全部替换 |
| `_mock_server_docs()` | ✅ 返回 MCPClient；✅ 含 search/get_version 工具 |
| `_mock_server_deploy()` | ✅ 返回 MCPClient；✅ 含 trigger/status 工具 |
| `connect_mcp()` | ✅ 正常连接；✅ 已连接重复不去重连；✅ 未知 server 返回错误 |
| `assemble_tool_pool()` | ✅ 仅内置工具；✅ 连接 docs 后追加 mcp__docs__* 工具；✅ handler 闭包正确调用 |

---

### 3.12 `test_bus.py` — MessageBus（~10 个测试）

| 测试点 | 方法 |
|--------|------|
| `MessageBus.send()` | ✅ 消息写入 JSONL；✅ 字段正确（from/to/content/type/ts） |
| `MessageBus.read_inbox()` | ✅ 有消息时读取并清空；✅ 无收件箱返回空列表；✅ 消费式读取 |
| `BUS` 是单例 | 直接检查 |
| `MAILBOX_DIR` 自动创建 | 删除后重新 import 模块 |

---

### 3.13 `test_protocol.py` — 协议系统（~15 个测试）

| 函数 | 测试点 |
|------|--------|
| `ProtocolState` | ✅ 默认值；✅ 字段赋值 |
| `new_request_id()` | ✅ 格式为 `req_XXXXXX`；✅ 每次生成不同 ID |
| `match_response()` | ✅ 正常匹配 shutdown_request→shutdown_response；✅ 正常匹配 plan_approval→plan_approval_response；✅ 类型不匹配拒绝；✅ 重复回复忽略；✅ 未知 request_id 忽略 |
| `consume_lead_inbox()` | ✅ 空收件箱；✅ 协议消息自动路由；✅ 纯消息不路由；✅ route_protocol=False |

---

### 3.14 `test_hooks.py` — 钩子系统（~15 个测试）

| 函数 | 测试点 |
|------|--------|
| `register_hook()` | ✅ 正常注册；✅ 同一事件注册多个回调 |
| `trigger_hooks()` | ✅ 无回调返回 None；✅ 依次调用所有回调；✅ 任一返回非 None 阻断后续；✅ 传参正确 |
| `permission_hook()` | ✅ bash + DENY_LIST 阻止；✅ bash + DESTRUCTIVE 提示（mock input）；✅ 非 bash 工具不阻止 |
| `log_hook()` | ✅ 返回 None（不阻断）；✅ 打印日志 |
| `large_output_hook()` | ✅ 小输出不打印；✅ 大输出打印警告；✅ 返回 None |
| `context_inject_hook()` | ✅ 返回 None |
| `summary_hook()` | ✅ 返回 None；✅ 正确统计 tool_result 数量 |

---

### 3.15 `test_worktree.py` — Worktree 隔离（~15 个测试）

| 函数 | 测试点 |
|------|--------|
| `validate_worktree_name()` | ✅ 合法名称通过；✅ 空字符串拒绝；✅ `.` / `..` 拒绝；✅ 含空格拒绝；✅ 超 64 字符拒绝 |
| `_count_worktree_changes()` | ✅ 无改动返回 (0, 0)；✅ 路径不存在返回 (-1, -1) |

**不需要测的**：`create_worktree()`, `remove_worktree()`（需要真实 git worktree，只在集成测试中验证）

---

### 3.16 `test_integration.py` — 集成测试（~10 个测试）

| 测试点 | 方法 |
|--------|------|
| 所有模块可正常 import | `import config; from core.utils import *; ...` |
| `BUILTIN_HANDLERS` 初始化后非空 | `from tools.builtin import init_builtin_handlers; init_builtin_handlers()` |
| `assemble_tool_pool()` 返回合理结果 | 连接 mock MCP 后检查工具池 |
| config + skills 联合 | 在临时 SKILLS_DIR 创建技能后 list_skills 可见 |
| config + tasks 联合 | create_task → list_tasks → claim → complete 完整流程 |
| config + memory 联合 | write_memory_file → read_memory_index → read_memory_file |
| config + cron 联合 | schedule_job → list → consume → cancel |
| config + bus + protocol 联合 | BUS.send → consume_lead_inbox → 协议路由 |
| hooks 实际注册验证 | import runtime.hooks 后 HOOKS["PreToolUse"] 非空 |

---

## 四、不能测试的东西

以下内容**跳过不测**，告诉用户原因：

| 内容 | 原因 |
|------|------|
| `agent_loop()` 主循环 | 依赖真实 Anthropic API + 用户交互，需要集成环境 |
| `spawn_subagent()` | 依赖真实 API 多轮调用 |
| `spawn_teammate_thread()` | daemon 线程 + API + 文件系统复杂交互 |
| `cron_scheduler_loop()` | 无限循环 daemon |
| `app.py` 的 `if __name__ == "__main__"` | 交互式，需要 stdin mock |
| `summarize_history()` 真实验证 | 需要真实 LLM 返回 |
| `select_relevant_memories()` 真实验证 | 需要真实 LLM 返回 |
| worktree create/remove 真实操作 | 需要真实 git 仓库环境 |

---

## 五、执行步骤

1. **创建 `tests/` 目录 + `conftest.py`**（fixtures 就位）
2. **从纯函数开始**：`test_utils.py` → `test_cron.py` → `test_recovery.py`（最稳定，改动最少）
3. **测文件 I/O**：`test_tasks.py` → `test_memory.py` → `test_skills.py`
4. **测状态机**：`test_protocol.py` → `test_hooks.py` → `test_bus.py`
5. **测复杂模块**：`test_compression.py` → `test_mcp.py` → `test_prompt.py`
6. **集成测试收尾**：`test_integration.py`
7. **运行全部测试**：`pytest tests/ -v`
8. **生成覆盖率报告**：`pytest tests/ --cov=. --cov-report=term-missing`

---

## 六、运行命令

```bash
cd d:\Agent\0-1claude

# 运行全部测试
pytest tests/ -v

# 只跑单个文件
pytest tests/test_utils.py -v

# 带覆盖率
pip install pytest-cov
pytest tests/ --cov=. --cov-report=term-missing

# 失败时停在第一条
pytest tests/ -x
```

---

## 七、验证清单

- [ ] 所有 test_*.py 文件创建完毕
- [ ] `pytest tests/ -v` 不报收集错误
- [ ] 测试通过率 ≥ 90%
- [ ] 没有测试依赖外部网络
- [ ] 没有测试修改真实文件系统（统一用 temp_workdir fixture）
- [ ] conftest.py mock 不影响原始模块行为（每次测试后 monkeypatch 自动恢复）
