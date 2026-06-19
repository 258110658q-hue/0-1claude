---
name: wait-30s-check-inbox
description: 用户要求在流程中等待30秒后检查收件箱
type: task
---

用户在规划或执行某任务时，指定了一个步骤：等待30秒后检查收件箱。助手在Windows环境下尝试使用`sleep`不可用，改用`timeout`命令执行等待操作，并最终以直接等待方式完成。
