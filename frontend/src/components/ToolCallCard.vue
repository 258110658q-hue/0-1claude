<template>
  <el-collapse class="tool-card" :model-value="['main']">
    <el-collapse-item name="main">
      <template #title>
        <span class="tool-head">
          <span class="dot" :class="{ pending: tool.pending }"></span>
          <span class="tool-name">{{ tool.name }}</span>
          <el-tag size="small" :type="tool.pending ? 'warning' : 'success'">
            {{ tool.pending ? '执行中' : '完成' }}
          </el-tag>
        </span>
      </template>

      <div class="tool-section">
        <div class="sec-label">入参</div>
        <pre class="kv">{{ inputText }}</pre>
      </div>
      <div class="tool-section" v-if="!tool.pending || tool.output">
        <div class="sec-label">结果</div>
        <pre class="kv out">{{ tool.output || '（无输出）' }}</pre>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tool: { type: Object, required: true },
})

const inputText = computed(() => {
  try {
    return JSON.stringify(props.tool.input ?? {}, null, 2)
  } catch (e) {
    return String(props.tool.input)
  }
})
</script>

<style scoped>
.tool-card {
  width: 78%;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fbfcfe;
  overflow: hidden;
}
.tool-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.tool-name {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-weight: 600;
  color: #34495e;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #67c23a;
}
.dot.pending {
  background: #e6a23c;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% {
    opacity: 0.3;
  }
}
.tool-section {
  margin-top: 8px;
}
.sec-label {
  font-size: 12px;
  color: var(--text-weak);
  margin-bottom: 4px;
}
.kv {
  margin: 0;
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 12.5px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
}
.kv.out {
  background: #f3f6f9;
}
</style>
