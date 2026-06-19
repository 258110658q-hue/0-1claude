# mes1 项目 README.md 编写提示词

请为 `d:\Agent\0-1claude` 下的 mes1 项目编写一份专业的 `README.md`。

**重要约束**：不要参考 `learn-claude-code/` 目录中的任何内容，完全基于 `mes1.py` 和拆分后的项目代码来编写。

---

## 一、README.md 内容大纲

按以下结构逐节编写，每节标注了必须覆盖的内容和行文风格：

### 1. 项目名称与徽章
- 标题：**mes1 — AI 编程智能体**
- 加上 Python 版本徽章、License 徽章（格式用 shields.io）

### 2. 项目概述
- 一句话定位：**Claude Code 核心机制复现项目**
- 用 3-5 句话说明这个项目做了什么、为什么值得关注
- 放上核心循环的 ASCII 流程图（从 mes1.py 顶部注释中提取，就是那个 `用户→大模型→工具→循环` 的图）


### 3. 快速开始
- 环境要求：Python 3.10+、Git
- 克隆仓库命令
- 创建虚拟环境 + 安装依赖：
  ```
  pip install anthropic python-dotenv pyyaml
  ```
- 配置 `.env` 文件（模板如下）：
  ```
  ANTHROPIC_API_KEY=sk-ant-xxx
  MODEL_ID=claude-sonnet-4-6
  # 可选：中转平台或 DeepSeek
  # ANTHROPIC_BASE_URL=https://your-proxy.com
  # FALLBACK_MODEL_ID=deepseek-chat
  ```
- 启动命令：`python app.py`

### 4. 项目架构
- 分层架构示意图（ASCII 图形）：
  ```
  app.py（入口）
  ├── core/          ← 核心引擎：循环、压缩、恢复、prompt 拼装
  ├── services/      ← 功能服务：技能、记忆、任务图、cron、后台任务
  ├── tools/         ← 工具系统：内置工具、子Agent、MCP、团队工具
  └── runtime/       ← 运行时：钩子、消息总线、协议、队友、worktree
  ```
- 每层一句话说明职责
- 完整文件树（21 个文件）

### 5. 核心机制一览

按功能领域分组，逐一介绍项目的全部能力。

#### 5.1 核心引擎

| 机制 | 说明 |
|------|------|
| Agent 循环 | while has_tool_use 循环：LLM 调用 → 工具执行 → 结果回传，直到模型认为任务完成 |
| 上下文压缩 | 四层压缩管线（snip → micro → budget → summarize），便宜的先跑、贵的后跑，0 API 调用处理到极限才用 LLM 摘要 |
| 错误恢复 | 三路径恢复：max_tokens 自动升级续写、prompt_too_long 应急压缩、429/529 指数退避 + 连续过载自动切换备用模型 |
| 分段 System Prompt | PROMPT_SECTIONS 按真实状态按需拼接，确定性缓存避免重复计算 |

#### 5.2 工具系统

| 机制 | 说明 |
|------|------|
| 多工具支持 | bash / read_file / write_file / edit_file / glob 五个基础工具，BUILTIN_HANDLERS 表驱动分发 |
| 子 Agent 派发 | task 工具启动子 Agent，全新上下文，只回传结论，中间过程全部丢弃 |
| MCP 外部工具 | MCPClient 服务发现 → 动态工具池组装，mcp__{server}__{tool} 前缀避免命名冲突 |

#### 5.3 安全控制

| 机制 | 说明 |
|------|------|
| 三级权限管道 | deny_list 拒绝列表 → rule_match 危险操作匹配 → user_approval 用户确认，层层过滤 |
| 钩子系统 | PreToolUse / PostToolUse / Stop 事件钩子，扩展逻辑从循环中解耦 |

#### 5.4 知识管理

| 机制 | 说明 |
|------|------|
| 技能加载 | 两级知识注入：启动时扫描目录注入名称和简介（便宜），用到时加载完整内容（按需） |
| 持久记忆 | 文件存储 + 索引注入每轮对话 + LLM 自动提取新记忆 + 定期去重整理 |

#### 5.5 任务与调度

| 机制 | 说明 |
|------|------|
| 任务规划 | todo_write 内存看板，动手前列步骤，执行中更新状态 |
| 持久化任务图 | 文件持久化 Task 节点 + blockedBy 依赖管理 + claim/complete 状态机 + 自动解锁下游任务 |
| Cron 定时调度 | 五段式 cron 表达式 + 闹钟 daemon 线程 + 队列自动交付 + durable 跨会话持久化 |
| 后台任务 | 慢操作（install/build/test）自动识别并放入 daemon 线程，完成后以通知形式注入对话 |

#### 5.6 多 Agent 协作

| 机制 | 说明 |
|------|------|
| Agent Teams | MessageBus 文件收件箱 + 队友 daemon 线程并行工作，消息消费式读取 |
| 团队协议 | request_id 全链路追踪 + ProtocolState 状态机（pending→approved/rejected）+ 计划审批门控 |
| 自治 Agent | 空闲轮询收件箱和任务板、自动认领 pending 任务、WORK→IDLE→SHUTDOWN 三阶段生命周期 |
| Worktree 隔离 | git worktree 目录隔离，每个任务独立分支，任务绑定 + 事件审计 + 有改动时拒绝删除 |

- 挑 3 个最亮眼的机制各用 2-3 句话展开（建议：上下文压缩的四层设计、Agent Teams 的自治协作模式、MCP 的开放工具生态）

### 6. 配置说明
- 环境变量表格：

| 变量 | 必填 | 说明 |
|------|------|------|
| ANTHROPIC_API_KEY | ✅ | API 密钥 |
| MODEL_ID | ✅ | 模型 ID（claude-sonnet-4-6 等） |
| ANTHROPIC_BASE_URL | ❌ | 自定义 API 地址（中转平台/DeepSeek） |
| FALLBACK_MODEL_ID | ❌ | 连续 529 过载后切换的备用模型 |

- 支持的模型列表：Claude Sonnet/Opus/Haiku 系列、DeepSeek、及其他兼容 Anthropic API 的模型

### 7. 使用示例
- 每个示例用代码块展示用户输入和预期行为，5-6 个场景：
  1. **基础编程问答**：输入 "用 Python 写一个快速排序" → LLM 回复代码
  2. **读写文件**：输入 "读取 config.py 的前 10 行" → Agent 调用 read_file 工具
  3. **派发子 Agent**：输入 "同时审查 core/utils.py 和 services/tasks.py" → Agent 用 task 工具并行
  4. **定时任务**：输入 "每天早上 9 点提醒我 standup" → Agent 调用 schedule_cron
  5. **创建任务板**：输入 "规划一个用户登录系统的开发任务" → Agent 用 create_task 建依赖任务图
  6. **MCP 扩展**：输入 "连接 docs 文档服务" → Agent 调用 connect_mcp 发现外部工具

### 8. 开发指南
- **添加新工具**（3 步）：
  1. 在 `tools/builtin.py` 的 `BUILTIN_TOOLS` 中添加工具定义
  2. 在对应的 service/runtime 模块中编写 handler 函数
  3. 在 `init_builtin_handlers()` 中注册映射
- **添加新技能**：在 `skills/` 目录下创建 `技能名/SKILL.md`
- **添加新钩子**：调用 `register_hook("事件名", 回调函数)`
- **运行测试**：`pytest tests/ -v`

### 9. 已知限制
- 文件锁为简化实现，高并发场景需替换
- 没有用户身份认证系统
- MCP 为本地 mock 实现，真实使用需接入 stdio JSON-RPC

### 10. 后续计划
- Web 前端界面
- 真正的 MCP stdio 进程接入
- 多模态（图片/音频）支持

### 11. 许可证
- 用 MIT License（自动选择合适的开源协议）

---

## 二、编写风格要求

1. **中文为主**，技术术语保留英文（如 agent loop、worktree、MCP）
2. **语气**：专业但不过度正式，像个人开发者写的正经开源项目 README
3. **代码块**统一用 ````bash` 或 ````python` 包裹
4. **不要出现「教学」「学习」「练习」**等字样——这是一个正经项目
5. **不要提及 learn-claude-code** 或任何外部参考项目
6. **篇幅**：控制在一屏能扫完核心内容，详细表格放后面

---

## 三、输出要求

- 直接输出完整的 `README.md` 文件内容，写入 `d:\Agent\0-1claude\README.md`
- 写完后用 `Read` 工具确认一遍格式正确
