<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { showFailToast } from 'vant'
import { listTasks } from '../api'
import type { Task } from '../types'

const tasks = ref<Task[]>([])
const loading = ref(true)
const active = computed(() => tasks.value.filter(item => !['SUCCEEDED', 'FAILED', 'CANCELED'].includes(item.status)))
const waiting = computed(() => active.value.filter(item => ['QUEUED', 'WAITING_APPROVAL'].includes(item.status)))
onMounted(async () => {
  try { tasks.value = await listTasks() }
  catch { showFailToast('队列加载失败') }
  finally { loading.value = false }
})
</script>

<template>
  <section class="content-page">
    <header class="content-page-header"><div><p class="page-kicker">实时执行</p><h1>运行队列</h1><p>聊天不占用主任务并发；执行任务继续遵守每任务 8 个工作 Agent、全局 12 个工作 Agent。</p></div></header>
    <div class="project-summary-grid compact-grid"><article><span>活跃任务</span><strong>{{ active.length }}</strong></article><article><span>排队/审批</span><strong>{{ waiting.length }}</strong></article><article><span>可用工作 Agent</span><strong>12</strong></article></div>
    <div v-if="loading" class="workbench-empty compact">正在读取队列…</div>
    <div v-else-if="!active.length" class="workbench-empty compact">当前没有运行中的任务</div>
    <div class="queue-list">
      <RouterLink v-for="task in active" :key="task.id" :to="`/tasks/${task.id}`">
        <div class="queue-progress"><i :style="{ width: `${task.progress}%` }" /></div>
        <div><strong>{{ task.title }}</strong><p>{{ task.current_step || '等待执行' }}</p></div>
        <span>{{ task.status }} · {{ task.progress }}%</span>
      </RouterLink>
    </div>
  </section>
</template>
