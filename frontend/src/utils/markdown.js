import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false, // 不渲染原始 HTML，避免模型输出里的标签破坏页面
  linkify: true,
  breaks: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
      } catch (e) {
        /* ignore */
      }
    }
    return '' // 交给 markdown-it 默认转义处理
  },
})

export function renderMarkdown(text) {
  return md.render(text || '')
}
