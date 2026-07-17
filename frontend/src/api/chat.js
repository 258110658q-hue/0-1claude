// 与后端 /api/chat 的 SSE 通信层。
// 注意：后端用 POST 接收 {session_id, message}，所以不能用浏览器原生
// EventSource（只支持 GET）。这里用 fetch + ReadableStream 手动解析 SSE。

/**
 * 流式对话。返回一个异步迭代器，逐个产出事件对象：
 *   {type:'session', session_id}
 *   {type:'assistant_text', text}
 *   {type:'tool_use', id, name, input}
 *   {type:'tool_result', id, name, output}
 *   {type:'error', message}
 *   {type:'done'}
 *
 * @param {string|null} sessionId 已有会话 id；null 表示新建
 * @param {string} message 用户输入
 * @param {AbortSignal} [signal] 可中断
 */
export async function* streamChat(sessionId, message, signal) {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const j = await resp.json()
      if (j && j.detail) detail = j.detail
    } catch (e) {
      /* ignore */
    }
    throw new Error(detail)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 事件以空行（\n\n）分隔；每行形如 "data: {json}"
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const line = raw
        .split('\n')
        .find((l) => l.startsWith('data:'))
      if (!line) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        yield JSON.parse(payload)
      } catch (e) {
        // 单行解析失败不影响后续
      }
    }
  }
}
