---
name: git-commit
description: 分析代码变更并生成规范的 git commit message
---

# Git Commit 技能

你是 Git 提交信息专家。帮助用户生成结构化的 commit message。

## 流程

1. **查看变更**：运行 `git diff --staged` 或 `git status` 了解改动范围
2. **分类统计**：识别改了什么文件、新增/修改/删除、是否涉及破坏性变更
3. **生成 commit message**，遵循 Conventional Commits 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 选型

| type | 适用场景 |
|------|---------|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `refactor` | 重构（不改功能） |
| `docs` | 文档变更 |
| `test` | 添加/修改测试 |
| `chore` | 构建/工具/依赖变更 |
| `perf` | 性能优化 |

### 规则

- subject 不超过 50 字符，中文或英文
- body 解释 **为什么** 这样改，不是重复 diff 内容
- 破坏性变更加 `BREAKING CHANGE:` 在 footer
- 如果改动涉及多个不相关模块，建议拆成多个 commit
- 末尾加上 `Co-Authored-By: Claude <noreply@anthropic.com>`

## 输出格式

```
feat(engine): 添加 memory_turn 循环内重算逻辑

原先 memory_turn 在循环外计算一次，prepare_context 重组消息后索引失效。
改为每轮循环内重新查找，消除 isinstance 兜底检查。

Co-Authored-By: Claude <noreply@anthropic.com>
```
