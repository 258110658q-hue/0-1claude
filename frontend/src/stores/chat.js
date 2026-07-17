import { defineStore } from 'pinia'
import { streamChat } from '../api/chat.js'

export const useChatStore = defineStore('chat', {
  state: () => ({
    // 会话元信息列表（来自 /api/sessions）
    sessions: [],
    // 当前选中的会话 id（本地新建时为 'local-...'，服务端建好后替换为真实 id）
    currentId: null,
    // id -> { messages: [], streaming: bool }
    conversations: {},
    // 模型名（来自 /api/info）
    model: '',
  }),

  getters: {
    currentConv(state) {
      return state.currentId ? state.conversations[state.currentId] : null
    },
  },

  actions: {
    async loadInfo() {
      try {
        const r = await fetch('/api/info')
        const d = await r.json()
        this.model = d.model
      } catch (e) {
        /* 后端未启动时忽略 */
      }
    },

    async loadSessions() {
      try {
        const r = await fetch('/api/sessions')
        this.sessions = await r.json()
      } catch (e) {
        /* ignore */
      }
    },

    ensureConv(id) {
      if (!this.conversations[id]) {
        this.conversations[id] = { messages: [], streaming: false }
      }
      return this.conversations[id]
    },

    newSession() {
      const id = 'local-' + Date.now().toString(36)
      this.conversations[id] = { messages: [], streaming: false }
      this.sessions.unshift({
        id,
        title: '新会话',
        message_count: 0,
        updated_at: Date.now() / 1000,
      })
      this.currentId = id
      return id
    },

    selectSession(id) {
      this.currentId = id
      this.ensureConv(id)
    },

    async deleteSession(id) {
      try {
        await fetch('/api/sessions/' + id, { method: 'DELETE' })
      } catch (e) {
        /* ignore */
      }
      delete this.conversations[id]
      this.sessions = this.sessions.filter((s) => s.id !== id)
      if (this.currentId === id) this.currentId = null
    },

    // 把本地临时会话映射到服务端返回的真实 id
    remapSession(localId, realId) {
      if (localId === realId) return
      this.conversations[realId] = this.conversations[localId]
      delete this.conversations[localId]
      const s = this.sessions.find((x) => x.id === localId)
      if (s) {
        s.id = realId
      } else {
        this.sessions.unshift({
          id: realId,
          title: '新会话',
          message_count: 0,
          updated_at: Date.now() / 1000,
        })
      }
      this.currentId = realId
    },

    async sendMessage(text) {
      const trimmed = (text || '').trim()
      if (!trimmed) return

      let id = this.currentId
      if (!id) id = this.newSession()
      else this.ensureConv(id)

      const conv = this.conversations[id]
      if (conv.streaming) return
      conv.streaming = true
      // 用户消息立即上屏
      conv.messages.push({ type: 'user', content: trimmed })

      let activeAssistant = null // 当前正在追加文本的助手气泡
      const toolMap = {} // tool_use_id -> 工具卡片对象

      try {
        const sessionArg = id.startsWith('local-') ? null : id
        for await (const ev of streamChat(sessionArg, trimmed)) {
          switch (ev.type) {
            case 'session':
              if (ev.session_id && ev.session_id !== id) {
                this.remapSession(id, ev.session_id)
                id = ev.session_id
              }
              break
            case 'assistant_text':
              if (!activeAssistant) {
                activeAssistant = { type: 'assistant', content: '' }
                conv.messages.push(activeAssistant)
              }
              activeAssistant.content += ev.text
              break
            case 'tool_use':
              // 工具调用到来，关闭当前文本气泡
              activeAssistant = null
              {
                const t = {
                  type: 'tool',
                  id: ev.id,
                  name: ev.name,
                  input: ev.input,
                  output: '',
                  pending: true,
                }
                toolMap[ev.id] = t
                conv.messages.push(t)
              }
              break
            case 'tool_result':
              {
                const t = toolMap[ev.id]
                if (t) {
                  t.output = ev.output
                  t.pending = false
                }
              }
              break
            case 'error':
              conv.messages.push({ type: 'error', content: ev.message })
              break
            case 'done':
              break
          }
        }
      } catch (e) {
        conv.messages.push({ type: 'error', content: '请求失败：' + e.message })
      } finally {
        conv.streaming = false
        const s = this.sessions.find((x) => x.id === id)
        if (s) {
          if (s.title === '新会话') s.title = trimmed.slice(0, 30)
          s.message_count = conv.messages.length
        }
        this.loadSessions()
      }
    },
  },
})
