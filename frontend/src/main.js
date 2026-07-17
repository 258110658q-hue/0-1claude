import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'highlight.js/styles/github.css'
import App from './App.vue'
import './styles/main.css'

createApp(App).use(createPinia()).use(ElementPlus).mount('#app')
