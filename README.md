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

## 许可证

[MIT](LICENSE)
