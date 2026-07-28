import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'vant/lib/index.css'
import './styles.css'
import './workspace.css'
import App from './App.vue'
import { router } from './router'

type Theme = 'light' | 'dark'
const savedTheme = localStorage.getItem('miniswarm:theme')
const initialTheme: Theme = savedTheme === 'dark' ? 'dark' : 'light'
document.documentElement.dataset.theme = initialTheme
document.documentElement.classList.toggle('van-theme-dark', initialTheme === 'dark')

createApp(App).use(createPinia()).use(router).mount('#app')
