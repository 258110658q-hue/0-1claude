<template>
  <el-container class="app-root">
    <ChatSidebar />
    <ChatWindow />
  </el-container>
</template>

<script setup>
import { onMounted } from 'vue'
import { useChatStore } from './stores/chat.js'
import ChatSidebar from './components/ChatSidebar.vue'
import ChatWindow from './components/ChatWindow.vue'

const store = useChatStore()
onMounted(() => {
  store.loadInfo()
  store.loadSessions()
})
</script>
