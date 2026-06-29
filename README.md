# mes1 — AI 编程智能体

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Claude Code 核心机制复现项目**——一个单仓库、多层架构的 AI 编程智能体，支持多工具调用、多 Agent 协作、上下文压缩、持久记忆、MCP 外部工具接入。

```
+----------+      +-------+      +---------+
|   用户    | ---> | 大模型 | ---> |  工具    |
|   提问    |      |       |      |  执行    |
+----------+      +---+---+      +----+----+
                      ^               |
                      |   工具执行结果  |
                      +---------------+
                      （循环继续）
```

Agent 把工具执行结果不断喂回模型，直到模型认为问题解决，不再调用工具为止。

---

## 快速开始

### 环境要求

- Python 3.10+
- Git（worktree 功能需要）

```bash
git clone <repo-url>
cd 0-1claude
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install anthropic python-dotenv pyyaml
```

### 配置

在项目根目录创建 `.env` 文件：

```bash
ANTHROPIC_API_KEY=sk-ant-xxx
MODEL_ID=claude-sonnet-4-6
# 可选：中转平台或 DeepSeek
# ANTHROPIC_BASE_URL=https://your-proxy.com
# FALLBACK_MODEL_ID=deepseek-chat
```

### 启动

```bash
python app.py
```

---

## 项目架构

```
app.py（入口）
├── core/          ← 核心引擎：循环、压缩、恢复、prompt 拼装
├── services/      ← 功能服务：技能、记忆、任务图、cron、后台任务
├── tools/         ← 工具系统：内置工具、子Agent、MCP、团队工具
└── runtime/       ← 运行时：钩子、消息总线、协议、队友、worktree
```

### 完整文件树

```
0-1claude/
├── app.py                    # 主入口
├── config.py                 # 全局配置
├── core/
│   ├── utils.py              # 工具函数（safe_path, run_*, has_tool_use …）
│   ├── prompt.py             # System Prompt 组装
│   ├── compression.py        # 四层上下文压缩
│   ├── recovery.py           # 错误恢复（指数退避、模型切换）
│   └── engine.py             # agent_loop 核心循环
├── services/
│   ├── skills.py             # 技能扫描/加载
│   ├── memory.py             # 记忆读写/检索/整理
│   ├── tasks.py              # 任务图 CRUD + 依赖管理
│   ├── cron.py               # Cron 调度（解析/匹配/持久化）
│   └── background.py         # 后台任务线程
├── tools/
│   ├── builtin.py            # 工具定义 + handler 映射
│   ├── subagent.py           # 子 Agent 派发
│   ├── team.py               # 团队/worktree/MCP handler
│   └── mcp.py                # MCP 插件系统
├── runtime/
│   ├── hooks.py              # 钩子系统 + 权限检查
│   ├── bus.py                # MessageBus 文件收件箱
│   ├── protocol.py           # 协议状态机
│   ├── teammate.py           # 队友自治循环
│   └── worktree.py           # git worktree 隔离
└── tests/                    # 194 个单元测试
```

---

## 核心机制一览

### 核心引擎

| 机制 | 说明 |
|------|------|
| Agent 循环 | `while has_tool_use` 循环：LLM 调用 → 工具执行 → 结果回传，直到模型认为任务完成 |
| 上下文压缩 | 四层压缩管线（snip → micro → budget → summarize），便宜的先跑、贵的后跑，0 API 调用处理到极限才用 LLM 摘要 |
| 错误恢复 | 三路径恢复：max_tokens 自动升级续写、prompt_too_long 应急压缩、429/529 指数退避 + 连续过载自动切换备用模型 |
| 分段 System Prompt | PROMPT_SECTIONS 按真实状态按需拼接，记忆、技能、MCP 状态动态注入 |

### 工具系统

| 机制 | 说明 |
|------|------|
| 多工具支持 | bash / read_file / write_file / edit_file / glob 五个基础工具，BUILTIN_HANDLERS 表驱动分发 |
| 子 Agent 派发 | task 工具启动子 Agent，全新上下文，只回传结论，中间过程全部丢弃 |
| MCP 外部工具 | MCPClient 服务发现 → 动态工具池组装，mcp__{server}__{tool} 前缀避免命名冲突 |

### 安全控制

| 机制 | 说明 |
|------|------|
| 三级权限管道 | deny_list 拒绝列表 → rule_match 危险操作匹配 → user_approval 用户确认，层层过滤 |
| 钩子系统 | PreToolUse / PostToolUse / Stop 事件钩子，扩展逻辑从循环中解耦 |

### 知识管理

| 机制 | 说明 |
|------|------|
| 技能加载 | 两级知识注入：启动时扫描目录注入名称和简介（便宜），用到时加载完整内容（按需） |
| 持久记忆 | 文件存储 + 索引注入每轮对话 + LLM 自动提取新记忆 + 定期去重整理 |

### 任务与调度

| 机制 | 说明 |
|------|------|
| 任务规划 | todo_write 内存看板，动手前列步骤，执行中更新状态 |
| 持久化任务图 | 文件持久化 Task 节点 + blockedBy 依赖管理 + claim/complete 状态机 + 自动解锁下游任务 |
| Cron 定时调度 | 五段式 cron 表达式 + 闹钟 daemon 线程 + 队列自动交付 + durable 跨会话持久化 |
| 后台任务 | 慢操作（install/build/test）自动识别并放入 daemon 线程，完成后以通知形式注入对话 |

### 多 Agent 协作

| 机制 | 说明 |
|------|------|
| Agent Teams | MessageBus 文件收件箱 + 队友 daemon 线程并行工作，消息消费式读取 |
| 团队协议 | request_id 全链路追踪 + ProtocolState 状态机（pending→approved/rejected）+ 计划审批门控 |
| 自治 Agent | 空闲轮询收件箱和任务板、自动认领 pending 任务、WORK→IDLE→SHUTDOWN 三阶段生命周期 |
| Worktree 隔离 | git worktree 目录隔离，每个任务独立分支，任务绑定 + 事件审计 + 有改动时拒绝删除 |

---

## 三大亮点

### 1. 四层上下文压缩——0 API 调用处理 80% 的场景

压缩管线按成本排序：先用 snip（裁中间消息）和 micro（旧结果占位符）处理，0 API 调用；实在不够再用 LLM 做全量摘要。大部分对话在 0 API 消耗下完成压缩，只在极端情况才调用模型。

### 2. Agent Teams——自己看板、自己认领、自己关机

Lead 创建任务、招队友之后就可以不管了。队友在 IDLE 阶段每 5 秒轮询任务板，发现 pending + 无 owner + 依赖满足的任务就自动认领。做完当前任务继续扫描下一个，60 秒无事可做才优雅关机。整个过程 Lead 不需要手动分配。

### 3. MCP——外部工具通过标准协议接入

外部服务只要实现 `tools/list` + `tools/call` 两个接口，Agent 就能发现和调用它们。工具池在运行时动态组装，`connect_mcp("docs")` 后立刻出现 `mcp__docs__search`，和内置工具完全一样使用。不管服务用什么语言写，Agent 不需要知道。

---

## 配置说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | API 密钥 |
| `MODEL_ID` | ✅ | 模型 ID（claude-sonnet-4-6 / claude-opus-4-8 / deepseek-chat 等） |
| `ANTHROPIC_BASE_URL` | ❌ | 自定义 API 地址（中转平台） |
| `FALLBACK_MODEL_ID` | ❌ | 连续 529 过载后自动切换的备用模型 |

支持 Claude Sonnet / Opus / Haiku 系列、DeepSeek、及其他兼容 Anthropic Messages API 的模型。

---

## 使用示例

### 基础编程问答

```bash
s20 >> 用 Python 写一个快速排序
```
Agent 回复完整代码实现。

### 读写文件

```bash
s20 >> 读取 core/utils.py 的前 20 行
```
Agent 调用 `read_file` 工具返回文件内容。

### 派发子 Agent

```bash
s20 >> 用子 Agent 扫描 core/ 目录下每个 .py 文件的函数定义
```
Agent 调用 `task` 工具启动子 Agent，子 Agent 独立工作，只回传结论。

### 定时提醒

```bash
s20 >> 设置一个一次性提醒，2 分钟后提醒我喝水
```
Agent 调用 `schedule_cron` 计算正确的时间表达式，到点自动弹出提醒。

### 任务板 + 依赖管理

```bash
s20 >> 创建 3 个任务：设计数据库 → 写 API（依赖数据库）→ 写测试（依赖 API）
```
Agent 用 `create_task` 建任务图，下游任务自动被阻塞，等待前置完成。

### 多 Agent 自治协作

```bash
s20 >> 创建 3 个后端任务，启动 alice 和 bob 自己认领去做
```
alice 和 bob 自动认领任务，互发消息协调分工，完成后发总结到 Lead 收件箱。

### MCP 外部工具

```bash
s20 >> 连接 docs MCP server，搜索 agent_loop 相关文档
```
Agent 调用 `connect_mcp` 发现外部工具，随后用 `mcp__docs__search` 检索文档。

---

## 开发指南

### 添加新工具

1. 在 `tools/builtin.py` 的 `BUILTIN_TOOLS` 中添加工具定义
2. 在对应的模块中编写 handler 函数
3. 在 `init_builtin_handlers()` 中注册映射

### 添加新技能

在 `skills/` 目录下创建 `技能名/SKILL.md`，使用 YAML frontmatter 声明名称和描述。

### 添加新钩子

```python
from runtime.hooks import register_hook
register_hook("PreToolUse", my_permission_check)
```

### 运行测试

```bash
pytest tests/ -v
```

---

## 已知限制

- MessageBus 和任务系统使用文件锁简化实现，高并发场景下存在竞争条件
- 没有用户身份认证系统，所有 Agent 共享同一权限级别
- MCP 为本地 mock 实现（Python 函数），真实使用需接入子进程 stdio JSON-RPC
- 上下文压缩在超长对话（>100 轮）下可能丢失关键信息

---

## 后续计划

- Web 前端界面
- MCP stdio 子进程接入（替换 mock）
- 多模态（图片/音频）支持
- 会话持久化与恢复

---

## 附录：Prompt Engineering 设计文档

### A. 使用的 Prompt 结构

项目中共有 **4 类 Prompt 结构**，各自服务于不同场景：

#### A.1 主 Agent System Prompt（`core/prompt.py`）

```
┌─────────────────────────────────────────┐
│  PROMPT_SECTIONS（固定模板）              │
│  ├─ identity:     "你是在 /path 工作的     │
│  │                编程智能体"              │
│  ├─ skills_instruction（始终注入）        │
│  ├─ memory_instruction（有记忆才注入）     │
│  └─ mcp_instruction（始终注入）           │
├─────────────────────────────────────────┤
│  动态注入（每轮实时拼装）                  │
│  ├─ skills_catalog（存在技能目录时）       │
│  ├─ memories（MEMORY.md 非空时）          │
│  └─ mcp_names（有连接时）                 │
└─────────────────────────────────────────┘
```

最终组装结果示例：

```
你是在 D:\Agent\0-1claude 工作的编程智能体。

可用技能：
- code-review: 代码审查
- deploy: 部署到生产环境

需要时使用 load_skill 获取技能的完整内容。

可用记忆：
- [用户偏好pytest](user-preference-pytest.md) — 用户偏好使用 pytest
- [项目结构](project-structure.md) — 采用四层架构 core/services/tools/runtime

相关记忆会在每轮自动注入。当用户说'记住'或表达明确偏好时，提取为记忆。

使用 connect_mcp 连接外部 MCP server。连接后 MCP 工具以 mcp__{server}__{tool} 格式可用。

已连接的 MCP server: docs
```

#### A.2 子 Agent System Prompt（`SUB_SYSTEM`）

```python
SUB_SYSTEM = (
    f"你是在 {WORKDIR} 工作的编程智能体。"
    "完成交给你的任务，然后返回简洁的总结。"
    "不要进一步委派。"          # ← 关键约束：禁止递归 spawn
)
```

极简设计：不加载技能、记忆、MCP。只给 5 个基础工具，30 轮上限，中间过程丢弃，只回传最终结论。

#### A.3 队友 Agent System Prompt

```python
system = (
    f"你是 '{name}'，一名 {role}。"    # ← 角色注入
    f"用工具完成任务。通过 send_message 向 'lead' 汇报。"
    f"你可以列出和认领任务板上的任务。"
    f"如果任务绑定了 worktree，就在那个目录下工作。"
    f"检查收件箱中的协议消息（shutdown_request 等）。"
)
```

#### A.4 记忆提取 Prompt（`services/memory.py`）

发给 LLM 的**侧查询**（side-query），不影响主对话流：

```python
# 记忆选择 Prompt
"根据最近的对话和下面的记忆目录，选出明显相关的记忆的索引。
 只返回 JSON 整数数组，如 [0, 3]。都不相关则返回 []。"

# 记忆提取 Prompt
"从以下对话中提取用户偏好、约束或项目事实。
 返回 JSON 数组。每项：{name, type, description, body}。
 如果没有新内容或已有记忆已覆盖，返回 []。"

# 记忆整理 Prompt
"整理以下记忆文件。规则：
 1. 合并内容重复的记忆
 2. 删除已过时或被新记忆覆盖的
 3. 总数控制在 30 条以内
 4. 优先保留用户偏好类记忆
 返回 JSON 数组。"
```

---

### B. 为什么这样设计

#### B.1 分段拼装 vs 一大段硬编码

| 维度 | 一大段硬编码（旧方案） | 分段拼装（当前方案） |
|------|---------------------|-------------------|
| 记忆不存在时 | prompt 里仍有"可用记忆："空段落 | 整段跳过，不占 token |
| MCP 未连接时 | "已连接 MCP server: " 空列表 | 整段跳过 |
| 加新能力 | 改 `build_system()` 函数体 | `PROMPT_SECTIONS` 加一个 key + `assemble_system_prompt` 加一个 if 块 |
| 单次变更影响面 | 整个 prompt 重新拼，缓存失效 | 只有变的部分重算 |

**核心设计原则**：System Prompt 的每一段都有"是否注入"的判断条件，基于真实运行时状态而非消息关键词。

#### B.2 为什么去掉 Prompt 缓存（s19）

s10 引入了 `get_system_prompt()` 的 JSON 确定性缓存——context 不变就不重新拼字符串。s19 去掉了缓存，原因：

- `connect_mcp` 后工具池动态变化（多了 `mcp__docs__search` 等工具）
- `assemble_tool_pool()` 需要每次重建工具列表
- 缓存中的旧工具列表会导致 LLM 不知道新工具的存在

**代价**：每次 `agent_loop` 开头多几毫秒的字符串拼接。**收益**：MCP 工具连接后立刻可用，不需要重启。

#### B.3 为什么记忆注入放在 User 消息而非 System Prompt

```
User Message:
<relevant_memories>
  [用户偏好pytest] 用户偏好使用 pytest 做测试...
  [项目结构] 采用四层架构 core/services/tools/runtime...
</relevant_memories>

帮我写一个测试文件
```

而不是放在 System Prompt 中。理由：

1. **Token 效率**：System Prompt 每轮都带，记忆只在相关时才注入（最多 5 条）
2. **上下文窗口**：LLM 对 System Prompt 的注意力衰减比 User 消息快
3. **压缩友好**：compact_history 压缩的是 messages，System Prompt 不好参与

---

### C. 是否使用 Few-shot 示例

**没有使用 Few-shot 示例。** 原因：

1. **工具定义 (JSON Schema) 自描述**：27 个工具的 `description` 和 `input_schema` 已经足够 LLM 理解何时调用
2. **System Prompt 指令式**：用 "当用户说'记住'时提取为记忆" 而非给 3 个示例
3. **Token 预算**：27 个工具定义本身已占 ~3000 token，加 few-shot 会进一步挤压有效上下文

**少数例外**（本质上不是 few-shot 而是**格式化约束**）：

- 记忆提取 prompt 中 `"返回 JSON 数组，如 [0, 3]。都不相关则返回 []"`
- cron 校验错误消息中 `"如现在是 14:30 就用 '31 14 * * *'"`

这些是针对**单一参数**的格式举例，不是完整的 few-shot 对话对。

---

### D. 如何控制输出格式

| 场景 | 控制方式 | 代码位置 |
|------|---------|---------|
| **工具调用** | JSON Schema `input_schema`：required 字段、enum 值、类型约束 | `tools/builtin.py` `BUILTIN_TOOLS` |
| **记忆提取** | `返回 JSON 数组。每项：{name, type, description, body}` | `services/memory.py` `extract_memories` |
| **记忆选择** | `只返回 JSON 整数数组，如 [0, 3]。都不相关则返回 []` | `services/memory.py` `select_relevant_memories` |
| **记忆整理** | `返回 JSON 数组。每项：{name, type, description, body}` | `services/memory.py` `consolidate_memories` |
| **压缩摘要** | `保留：1.当前目标 2.关键发现/决策 3.已读取/修改的文件 4.剩余工作 5.用户约束` | `core/compression.py` `summarize_history` |
| **子 Agent** | `完成交给你的任务，然后返回简洁的总结。不要进一步委派。` | `core/prompt.py` `SUB_SYSTEM` |

---

### E. 如何处理模型不确定、越界回答或格式错误

#### E.1 格式错误——正则提取 + 降级策略

```python
# 记忆提取：正则匹配 JSON 数组，失败则静默跳过
match = re.search(r'\[.*\]', text, re.DOTALL)
if not match:
    return  # ← 静默跳过，不中断对话

# 记忆选择：LLM 返回失败 → 降级为关键词匹配
except Exception:
    pass  # ← 降级：用 recent.split() 做关键词匹配 name+description
```

**设计理念**：侧查询（记忆提取/选择/整理）的失败**不能影响主对话流**。所有都包在 `try/except` 中，失败静默降级。

#### E.2 模型不确定——工具 Schema 约束

```python
# todo_write 的 status 字段用 enum 约束
"status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}

# review_plan 的 approve 字段用 boolean
"approve": {"type": "boolean"}

# 一次性 cron 拒绝 "每分钟都触发" 的表达式
if not recurring and fields[0] == '*' and fields[1] == '*':
    return "一次性 cron 需要指定具体分钟和小时..."
```

LLM 不确定时传了无效值 → handler 校验并返回清晰的错误消息 → LLM 看到错误后重试。

#### E.3 越界回答——三级权限管道

| 层级 | 检查内容 | 行为 |
|------|---------|------|
| deny_list | `rm -rf /`、`sudo`、`mkfs` | **直接拒绝**，不询问 |
| DESTRUCTIVE | `rm `、`chmod 777` | **弹窗确认**，用户选 y/N |
| 路径越界 | `../` 穿透 WORKDIR | **抛异常拒绝** |
| MCP 部署 | `mcp__deploy__*` | **弹窗确认** |

#### E.4 续写断点——max_tokens 恢复

```python
if response.stop_reason == "max_tokens":
    if not state.has_escalated:
        max_tokens = 64000           # 第1次: 8K→64K 重试
    elif state.recovery_count < 3:
        messages.append("从中断处接着写")  # 第2-4次: 续写提示
```

---

### F. Prompt 修改前后效果对比

#### 对比 1：System Prompt 从硬编码到分段拼装

| 维度 | 修改前 (s09) | 修改后 (s10-s19) |
|------|------------|-----------------|
| 结构 | `build_system()` 返回一个大字符串 | `PROMPT_SECTIONS` 字典 + `assemble_system_prompt(context)` 动态拼接 |
| 记忆不存在时 | 每次都出现 "相关记忆会在每轮自动注入" | 只在 `MEMORY.md` 非空时才注入记忆段落 |
| MCP 未连接时 | 无此概念 | 不注入 MCP 段落，节省 ~80 token |
| 加新段落 | 改 `build_system()` 函数体，需重新测试整段 | 加一个 dict key + 一个 if 块，只测新增部分 |
| **实测效果** | 空状态 prompt 约 200 字符 | 空状态 prompt 约 120 字符，**节省 40% token** |

#### 对比 2：技能加载从全量注入到两级按需

| 维度 | 修改前 | 修改后 (s07) |
|------|--------|------------|
| System Prompt 中的技能信息 | 全文注入（每个技能 ~2000 token） | 只有名称+一句话描述（~50 token/技能） |
| 加载时机 | 启动时全部加载 | `load_skill(name)` 按需加载 |
| 5 个技能场景 | System Prompt ~10,000 token | System Prompt ~250 token + 用到时 ~2000 token |
| **实测效果** | 5 个技能直接撑爆上下文 | **节省 97.5% 的常驻 token**，只在真正需要时才加载 |

#### 对比 3：MCP 连接前后

| 维度 | 连接前 | 连接后 |
|------|-------|-------|
| System Prompt | `使用 connect_mcp 连接外部 MCP server...` | 同上 + `已连接的 MCP server: docs` |
| 工具列表 | 21 个内置工具 | 23 个（+ `mcp__docs__search` + `mcp__docs__get_version`） |
| LLM 能否调用 MCP 工具 | 否（不知道存在） | 是（工具池已更新） |
| **实测效果** | 输入 "搜索文档" → LLM 说做不到 | 输入 "搜索文档" → LLM 直接调 `mcp__docs__search("query")` |

#### 对比 4：记忆注入位置

| 维度 | System Prompt 注入（旧方案） | User Message 注入（当前方案） |
|------|--------------------------|---------------------------|
| Token 消耗 | 每轮 ~200 token（即使无关） | 仅相关轮 ~200 token，无关轮 0 |
| 压缩影响 | compact_history 后记忆丢失 | 记忆在 messages 中，压缩时被摘要保留 |
| LLM 注意力 | 较低（System Prompt 衰减快） | 较高（紧贴用户提问） |
| **实测效果** | 第 10 轮后 LLM 明显忽略记忆 | 第 20 轮 LLM 仍能根据 5 轮前的记忆调整回答 |

---

## 附录 B：Agent 系统设计文档

### B.1 Agent 基本概念

本项目是一个完整的 **AI Agent 系统**——在 LLM 基础上构建了可执行、可检索、可调用工具、可管理上下文的 AI 应用。它与 Chatbot 和 Workflow 的区别：

| 类型 | 特点 | 本项目对应 |
|------|------|----------|
| **Chatbot** | 偏对话，一问一答 | `agent_loop` 的 `stop_reason != tool_use` 分支——模型直接回复文本 |
| **Workflow** | 偏确定流程，按预设步骤执行 | `todo_write` + task graph 的 `blockedBy` 依赖链 |
| **Agent** | 偏动态决策和工具调用 | `agent_loop` 的 `has_tool_use` 分支——模型自主决定调用哪些工具、多少次 |

核心能力矩阵：

| 能力 | 本项目实现 | 对应模块 |
|------|----------|---------|
| Prompt 工程 | 分段拼装、动态注入、记忆侧查询 | `core/prompt.py` |
| RAG | 持久记忆文件 + LLM 语义选择 + 关键词降级 | `services/memory.py` |
| 工具调用 | 27 个内置工具 + MCP 动态扩展，JSON Schema 定义 | `tools/builtin.py`、`tools/mcp.py` |
| Workflow | 任务图 + blockedBy 依赖 + 自动解锁下游 | `services/tasks.py` |
| 状态管理 | 会话历史、任务进度、记忆索引、cron 持久化 | `services/cron.py`、`app.py` |
| 记忆 | 短期（当前对话）+ 长期（.memory/*.md 持久化）+ 定期整理 | `services/memory.py` |
| 评估 | 194 个单元测试，覆盖全部纯函数 | `tests/` |
| 安全 | 三级权限管道 + 钩子系统 + 沙箱路径约束 | `runtime/hooks.py` |

### B.2 Agent 核心循环

```
while True:
    ┌──────────────────────────────────────────────────────┐
    │ 1. 注入: cron 定时任务 + 后台任务通知 + nag 提醒    │
    │ 2. 压缩: budget→snip→micro→compact（四层管线）      │
    │ 3. 组装: System Prompt + 记忆 + 技能 + MCP 状态      │
    │ 4. 调用: LLM (tools=动态工具池, max_tokens, 重试)   │
    │ 5. 恢复: max_tokens 升级 / prompt_too_long 应急      │
    │    ┌─────────────────────────────────────────────┐   │
    │    │ has_tool_use?                                │   │
    │    │  ├─ Yes → PreToolUse hooks → 执行工具        │   │
    │    │  │   ├─ compact? → 摘要压缩 → 注入结果       │   │
    │    │  │   ├─ 后台任务? → daemon 线程 → 占位符     │   │
    │    │  │   └─ 同步? → 调 handler → tool_result     │   │
    │    │  │   └─ connect_mcp? → 重建工具池            │   │
    │    │  └─ No  → Stop hooks → 提取记忆 → 返回       │   │
    │    └─────────────────────────────────────────────┘   │
    │ 6. 追加: tool_result + 后台通知 → messages          │
    └──────────────────────────────────────────────────────┘
```

模型根据用户目标、上下文和工具结果持续推进任务，直到 `has_tool_use` 返回 False。

### B.3 工具调用设计

#### 工具定义（JSON Schema）

每个工具通过标准 JSON Schema 声明其接口，LLM 据此决定何时调用、传什么参数：

```python
# 示例：create_task 工具定义
{"name": "create_task",
 "description": "创建新任务。可指定 blockedBy 声明依赖。",
 "input_schema": {"type": "object",
                  "properties": {"subject": {"type": "string"},
                                 "description": {"type": "string"},
                                 "blockedBy": {"type": "array",
                                               "items": {"type": "string"}}},
                  "required": ["subject"]}}
```

#### 工具执行与错误处理

| 环节 | 处理方式 |
|------|---------|
| 工具选择 | LLM 根据 Schema 自主决策，无需枚举路由规则 |
| 参数校验 | `_normalize_todos` 校验格式/字段/枚举值，`schedule_job` 拒绝非法 cron |
| 执行超时 | `run_bash` 默认 120s 超时，`subprocess.TimeoutExpired` 返回错误消息 |
| 执行错误 | `call_tool_handler` 捕获 `TypeError`（参数不匹配）返回错误消息而非崩溃 |
| 结果截断 | `run_bash` 截断到 50000 字符，避免撑爆上下文 |
| 后台执行 | 慢操作（install/build）自动识别，daemon 线程异步执行，主循环不阻塞 |
| MCP 工具错误 | `MCPClient.call_tool` 捕获 handler 异常，返回 `MCP error: {e}` |

### B.4 Workflow 模式

本项目中内置了多种 Workflow 模式：

| 模式 | 说明 | 项目实现 |
|------|------|---------|
| **Prompt Chaining** | 一个 LLM 的输出作为下一个的输入 | 子 Agent→主 Agent 的结论回传 |
| **Routing** | 根据输入分类路由到不同处理器 | `BUILTIN_HANDLERS` 按工具名分发 handler |
| **Parallelization** | 多个任务并行执行 | 队友 daemon 线程并行工作 |
| **Orchestrator-Workers** | 一个主控分配任务给多个 worker | Lead 创建任务→spawn 队友→队友自动认领执行 |
| **Evaluator-Optimizer** | 评估输出质量并迭代改进 | 计划审批门控：队友提交计划→Lead 审批→队友执行 |

**核心设计原则**：可控流程优先于盲目 Agent 化。`todo_write` 和 task graph 提供了明确的任务拆分和执行约束，让 Agent 行为可预测、可审计。

### B.5 状态管理

| 状态类型 | 存储方式 | 生命周期 | 对应模块 |
|---------|---------|---------|---------|
| **会话历史** | 内存 `session_history: list` | 单次会话 | `app.py` |
| **任务进度** | 文件 `.runtime/tasks/task_*.json` | 跨会话持久化 | `services/tasks.py` |
| **记忆索引** | 文件 `.runtime/memory/MEMORY.md` | 跨会话持久化 | `services/memory.py` |
| **cron 定时** | 文件 `.runtime/scheduled_tasks.json` | 跨会话持久化 | `services/cron.py` |
| **当前 todos** | 内存 `CURRENT_TODOS: list` | 单次会话 | `core/utils.py` |
| **队友消息** | 文件 `.runtime/mailboxes/*.jsonl` | 消费式（读后即删） | `runtime/bus.py` |
| **worktree 事件** | 文件 `.runtime/worktrees/events.jsonl` | 跨会话 | `runtime/worktree.py` |
| **压缩存档** | 文件 `.runtime/transcripts/*.jsonl` | 跨会话 | `core/compression.py` |
| **协议状态** | 内存 `pending_requests: dict` | 单次会话 | `runtime/protocol.py` |

**设计理念**：关键状态（任务、记忆、cron）文件持久化，避免 Agent 变成不可复盘的黑盒。运行时可丢弃的状态（会话历史、协议请求）保留在内存中。

### B.6 记忆系统

遵循记忆和上下文的区分——上下文是当前对话窗口内的内容，记忆是跨会话保留的知识。

| 记忆类型 | 实现 | 说明 |
|---------|------|------|
| **短期记忆** | `messages[-20:]`（当前对话窗口） | LLM 直接看到的最近 20 条消息 |
| **长期记忆** | `.memory/*.md` 文件存储 | 跨会话持久化，YAML frontmatter 元数据 |
| **语义记忆** | LLM 侧查询根据对话内容选择相关记忆 | `select_relevant_memories()` |
| **记忆提取** | 每轮结束后 LLM 自动从对话中提取 | `extract_memories()` |
| **记忆压缩** | 文件数 ≥10 时触发 LLM 去重合并 | `consolidate_memories()` |
| **遗忘机制** | 整理时删除过时/被覆盖的记忆 | `consolidate_memories()` 的合并+删除规则 |

### B.7 上下文工程

控制模型在有限窗口内获得正确信息：

| 技术 | 实现 | API 消耗 |
|------|------|---------|
| **上下文预算** | `tool_result_budget`：单条结果 >30000 字符时落盘，上下文只留预览 | 0 |
| **上下文裁剪** | `snip_compact`：保留首尾消息，裁掉中间，不拆散 tool_use/tool_result 对 | 0 |
| **旧结果占位** | `micro_compact`：只保留最近 3 条完整 tool_result，更旧的替换为占位符 | 0 |
| **LLM 摘要** | `compact_history`：上下文仍超限时调用 LLM 生成摘要 | 1 |
| **应急压缩** | `reactive_compact`：API 报 prompt_too_long 时比 compact_history 更激进 | 1 |
| **动态注入** | 记忆/技能/MCP 状态根据运行时 context 按需拼入 System Prompt | 0 |

### B.8 Agent 安全

| 安全机制 | 实现 | 对应 OWASP 建议 |
|---------|------|---------------|
| **Prompt Injection 防御** | `safe_path` 拒绝 `../` 路径遍历；`validate_worktree_name` 白名单校验 | 输入校验 |
| **工具越权防护** | `DENY_LIST`（`rm -rf /`、`sudo`、`mkfs`）直接拒绝；`DESTRUCTIVE`（`rm`、`chmod 777`）需用户确认 | 工具权限控制 |
| **沙箱执行** | `safe_path` 强制所有文件操作在 WORKDIR 内 | 路径沙箱 |
| **敏感操作确认** | MCP 部署工具（`mcp__deploy__*`）弹窗要求用户确认 | 二次确认 |
| **外部内容不可信** | MCP 工具返回内容仅作为 tool_result 注入，不直接执行 | 输入隔离 |
| **关键操作审批** | 计划审批门控：队友 `submit_plan` 后暂停，等 Lead `review_plan` 批准才继续 | Human-in-the-Loop |

### B.9 Agent 评估

| 指标 | 本项目现状 |
|------|----------|
| **任务完成率** | 194 个单元测试全部通过，覆盖全部纯函数逻辑 |
| **工具调用准确率** | `call_tool_handler` 的错误路径已测试（handler 不存在/参数不匹配） |
| **步骤合理性** | `todo_write` + task graph 提供明确任务链，`blockedBy` 强制顺序约束 |
| **失败恢复** | 三路径错误恢复：max_tokens 升级→续写、prompt_too_long 应急压缩、429/529 指数退避+模型切换 |
| **多轮稳定性** | 上下文压缩管线确保超长对话不溢出窗口 |

### B.10 参考资源

本项目设计参考了以下业界实践：

- **Agent 核心循环**: [Claude Code Agent SDK - Agent Loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- **工具调用设计**: [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- **Workflow 模式**: [Building Effective Agents (Anthropic)](https://www.anthropic.com/engineering/building-effective-agents)
- **规划与任务拆解**: [LLM Powered Autonomous Agents (Lilian Weng)](https://lilianweng.github.io/posts/2023-06-23-agent/)
- **记忆系统**: [IBM - AI Agent Memory](https://www.ibm.com/think/topics/ai-agent-memory)
- **上下文工程**: [Effective Context Engineering (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **MCP**: [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)
- **Human-in-the-Loop**: [LangGraph Human-in-the-Loop](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
- **状态持久化**: [Durable Execution for AI Agents](https://www.inngest.com/blog/durable-execution-key-to-harnessing-ai-agents)
- **Agent 安全**: [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- **评估**: [Langfuse Evaluation](https://langfuse.com/docs/evaluation/overview)
- **源码参考**: [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)

---

## 许可证

[MIT](LICENSE)
