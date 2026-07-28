<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showFailToast } from 'vant'
import { searchWorkspace } from '../api'
import type { SearchItem } from '../types'

const route = useRoute()
const router = useRouter()
const query = ref(String(route.query.q || ''))
const results = ref<SearchItem[]>([])
const total = ref(0)
const searched = ref(false)
const loading = ref(false)

async function search() {
  const value = query.value.trim()
  if (!value) return
  loading.value = true
  try {
    const response = await searchWorkspace(value)
    results.value = response.items
    total.value = response.total
    searched.value = true
    router.replace({ query: { q: value } })
  } catch {
    showFailToast('搜索失败')
  } finally {
    loading.value = false
  }
}

function destination(item: SearchItem) {
  if (item.task_id) return `/tasks/${item.task_id}`
  if (item.project_id) return `/projects/${item.project_id}`
  if (item.kind === 'global_memory') return '/memories'
  return '/'
}

onMounted(() => { if (query.value) search() })
</script>

<template>
  <section class="content-page search-page">
    <header class="content-page-header"><div><p class="page-kicker">Ctrl/Cmd + K</p><h1>全局搜索</h1><p>搜索你有权限访问的项目、任务、对话、文件、来源和记忆。</p></div></header>
    <form class="global-search-box" @submit.prevent="search"><span>⌕</span><input v-model="query" autofocus placeholder="输入关键词…" /><button type="submit">{{ loading ? '搜索中' : '搜索' }}</button></form>
    <div v-if="searched" class="search-summary">找到 {{ total }} 项结果</div>
    <div v-if="searched && !results.length" class="workbench-empty compact">没有匹配结果</div>
    <div class="search-results">
      <RouterLink v-for="item in results" :key="`${item.kind}-${item.id}`" :to="destination(item)">
        <span class="search-kind">{{ item.kind }}</span><div><strong>{{ item.title }}</strong><p>{{ item.snippet }}</p></div><time v-if="item.updated_at">{{ new Date(item.updated_at).toLocaleDateString() }}</time>
      </RouterLink>
    </div>
  </section>
</template>
