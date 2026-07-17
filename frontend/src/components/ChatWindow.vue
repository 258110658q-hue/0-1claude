<template>
  <el-main class="chat-window">
    <div class="chat-head">
      <span class="title">对话</span>
      <span v-if="store.model" class="model-tag">模型：{{ store.model }}</span>
    </div>

    <MessageList v-if="conv" :messages="conv.messages" />
    <el-empty v-else description="在左侧新建或选择一个会话开始对话" />

    <ChatInput
      :disabled="conv && conv.streaming"
      @send="store.sendMessage"
    />
  </el-main>
</template>

<script setup>
import { computed } from 'vue'
import { useChatStore } from '../stores/chat.js'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'

const store = useChatStore()
const conv = computed(() => store.currentConv)
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  padding: 0;
  background: var(--bg);
  height: 100vh;
}
.chat-head {
  height: 52px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 18px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
}
.title {
  font-weight: 600;
}
.model-tag {
  font-size: 12px;
  color: var(--text-weak);
}
</style>
