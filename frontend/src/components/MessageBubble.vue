<template>
  <div class="bubble" :class="role" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '../utils/markdown.js'

const props = defineProps({
  role: { type: String, required: true }, // user | assistant | error
  content: { type: String, default: '' },
})

const html = computed(() => renderMarkdown(props.content))
</script>

<style scoped>
.bubble {
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--assistant-bubble);
  border: 1px solid var(--border);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.bubble.user {
  background: var(--user-bubble);
  border-color: transparent;
}
.bubble.error {
  background: #fef0f0;
  border-color: #fbc4c4;
  color: #f56c6c;
}
</style>
