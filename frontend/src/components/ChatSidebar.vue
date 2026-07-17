<template>
  <el-aside width="260px" class="sidebar">
    <div class="sidebar-head">
      <div class="brand">mes1 Web Agent</div>
      <div class="brand-sub">Claude Code 机制的 Python 复现</div>
    </div>

    <el-button type="primary" class="new-btn" @click="store.newSession()">
      + 新建对话
    </el-button>

    <div class="session-list">
      <div
        v-for="s in store.sessions"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === store.currentId }"
        @click="store.selectSession(s.id)"
      >
        <div class="session-title">{{ s.title || '新会话' }}</div>
        <span class="del" title="删除" @click.stop="onDelete(s)">×</span>
      </div>
      <el-empty
        v-if="store.sessions.length === 0"
        description="还没有会话"
        :image-size="60"
      />
    </div>
  </el-aside>
</template>

<script setup>
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '../stores/chat.js'

const store = useChatStore()

async function onDelete(s) {
  try {
    await ElMessageBox.confirm(`删除会话「${s.title || '新会话'}」？`, '提示', {
      type: 'warning',
    })
    store.deleteSession(s.id)
  } catch (e) {
    /* 取消 */
  }
}
</script>

<style scoped>
.sidebar {
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 14px 12px;
}
.sidebar-head {
  padding: 4px 6px 12px;
}
.brand {
  font-weight: 700;
  font-size: 16px;
}
.brand-sub {
  font-size: 12px;
  color: var(--text-weak);
  margin-top: 2px;
}
.new-btn {
  width: 100%;
  margin-bottom: 12px;
}
.session-list {
  flex: 1;
  overflow: auto;
}
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text);
}
.session-item:hover {
  background: #eef2f7;
}
.session-item.active {
  background: #e6f0ff;
  color: var(--accent);
  font-weight: 600;
}
.session-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.del {
  color: var(--text-weak);
  font-size: 18px;
  line-height: 1;
  padding: 0 4px;
  visibility: hidden;
}
.session-item:hover .del {
  visibility: visible;
}
.del:hover {
  color: #f56c6c;
}
</style>
