<template>
  <div class="chat-input">
    <el-input
      v-model="text"
      type="textarea"
      :rows="3"
      resize="none"
      :disabled="disabled"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
      @keydown.enter="onEnter"
    />
    <div class="actions">
      <span class="hint" v-if="disabled">回复中…</span>
      <el-button type="primary" :disabled="disabled || !text.trim()" @click="send">
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['send'])

const text = ref('')

function send() {
  const v = text.value.trim()
  if (!v) return
  emit('send', v)
  text.value = ''
}

function onEnter(e) {
  // Enter 发送；Shift+Enter 换行
  if (!e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<style scoped>
.chat-input {
  border-top: 1px solid var(--border);
  background: var(--panel);
  padding: 12px 18px 16px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-top: 8px;
}
.hint {
  font-size: 12px;
  color: var(--text-weak);
  margin-right: auto;
}
</style>
