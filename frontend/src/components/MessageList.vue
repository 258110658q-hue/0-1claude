<template>
  <div ref="listEl" class="message-list">
    <div
      v-for="(m, i) in messages"
      :key="i"
      class="msg-row"
      :class="m.type"
    >
      <template v-if="m.type === 'tool'">
        <ToolCallCard :tool="m" />
      </template>
      <template v-else>
        <div class="avatar">
          {{ m.type === 'user' ? '你' : m.type === 'error' ? '!' : 'AI' }}
        </div>
        <div class="bubble-wrap">
          <MessageBubble :role="m.type" :content="m.content" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import MessageBubble from './MessageBubble.vue'
import ToolCallCard from './ToolCallCard.vue'

const props = defineProps({
  messages: { type: Array, required: true },
})

const listEl = ref(null)

function scrollBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

// 消息数量或内容变化都滚到底部（流式追加时实时跟随）
watch(() => props.messages, scrollBottom, { deep: true })
onMounted(scrollBottom)
</script>

<style scoped>
.message-list {
  flex: 1;
  overflow: auto;
  padding: 18px 22px;
}
.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.msg-row.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}
.msg-row.user .avatar {
  background: #67c23a;
}
.msg-row.error .avatar {
  background: #f56c6c;
}
.bubble-wrap {
  max-width: 78%;
  min-width: 0;
}
.msg-row.user .bubble-wrap {
  display: flex;
  justify-content: flex-end;
}
</style>
