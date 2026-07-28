<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant'
import { listArchivedTasks, listProjects, restoreProject, restoreTask, retryArchiveAnalysis } from '../api'
import type { ArchivedTask, Project } from '../types'

const tasks = ref<ArchivedTask[]>([])
const projects = ref<Project[]>([])
const total = ref(0)
const loading = ref(true)
const query = ref('')
const memoryStatus = ref('')

const memoryLabels: Record<string, string> = {
  NOT_ANALYZED: '未分析',
  QUEUED: '等待整理',
  RUNNING: '整理中',
  SUCCEEDED: '已加入记忆',
  FAILED: '整理失败',
}

async function refresh() {
  loading.value = true
  try {
    const [result, allProjects] = await Promise.all([
      listArchivedTasks({
        q: query.value || undefined,
        memory_status: memoryStatus.value || undefined,
        limit: 100,
      }),
      listProjects(true),
    ])
    tasks.value = result.items
    const normalizedQuery = query.value.trim().toLocaleLowerCase()
    projects.value = allProjects.filter(project =>
      Boolean(project.archived_at) &&
      (!normalizedQuery ||
        project.name.toLocaleLowerCase().includes(normalizedQuery) ||
        project.description.toLocaleLowerCase().includes(normalizedQuery)),
    )
    total.value = result.total
  } catch {
    showFailToast('归档任务加载失败')
  } finally {
    loading.value = false
  }
}

async function restoreArchivedProject(project: Project) {
  try {
    await showConfirmDialog({
      title: '恢复项目空间',
      message: '项目、成员、文件、任务和项目记忆都会重新出现在项目列表中。',
    })
    await restoreProject(project.id)
    showSuccessToast('项目空间已恢复')
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
    await refresh()
  } catch (error: any) {
    if (error?.response) showFailToast(error.response.data?.detail || '项目恢复失败')
  }
}

async function restore(task: ArchivedTask) {
  try {
    await showConfirmDialog({
      title: '恢复任务',
      message: '任务会回到任务列表，已经形成的全局记忆会保留。',
    })
    await restoreTask(task.id)
    showSuccessToast('任务已恢复')
    await refresh()
  } catch (error: any) {
    if (error?.response) showFailToast(error.response.data?.detail || '恢复失败')
  }
}

async function retryMemory(task: ArchivedTask) {
  try {
    await retryArchiveAnalysis(task.id)
    showSuccessToast('已重新开始整理记忆')
    await refresh()
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '重新分析失败')
  }
}

onMounted(refresh)
</script>

<template>
  <section>
    <div class="hero-copy">
      <p class="eyebrow">历史资料库</p>
      <h1>归档任务</h1>
      <p class="muted">任务文件不会被删除；归档后会在后台整理可复用的全局记忆。</p>
    </div>

    <div class="filter-bar">
      <input v-model="query" placeholder="搜索标题或任务内容" @keyup.enter="refresh" />
      <select v-model="memoryStatus" @change="refresh">
        <option value="">全部记忆状态</option>
        <option value="NOT_ANALYZED">未分析</option>
        <option value="QUEUED">等待整理</option>
        <option value="RUNNING">整理中</option>
        <option value="SUCCEEDED">已加入记忆</option>
        <option value="FAILED">整理失败</option>
      </select>
      <button class="secondary-button" type="button" @click="refresh">查询</button>
    </div>

    <div class="section-heading">
      <h2>归档项目空间</h2>
      <span class="muted">共 {{ projects.length }} 项</span>
    </div>
    <div v-if="loading" class="empty-state">正在加载…</div>
    <div v-else-if="!projects.length" class="empty-state">没有符合条件的归档项目空间</div>
    <div v-else class="task-list">
      <article v-for="project in projects" :key="project.id" class="task-card archive-card">
        <div class="task-card-top">
          <strong>{{ project.name }}</strong>
          <span class="status-chip">项目空间</span>
        </div>
        <p>{{ project.description || '未填写项目说明' }}</p>
        <small>归档于 {{ new Date(project.archived_at || project.updated_at).toLocaleString() }}</small>
        <div class="action-row compact">
          <button class="secondary-button" type="button" @click="restoreArchivedProject(project)">恢复项目空间</button>
        </div>
      </article>
    </div>

    <div class="section-heading">
      <h2>归档记录</h2>
      <span class="muted">共 {{ total }} 项</span>
    </div>
    <div v-if="loading" class="empty-state">正在加载…</div>
    <div v-else-if="!tasks.length" class="empty-state">没有符合条件的归档任务</div>
    <div v-else class="task-list">
      <article v-for="task in tasks" :key="task.id" class="task-card archive-card">
        <div class="task-card-top">
          <strong>{{ task.title }}</strong>
          <span class="status-chip">{{ memoryLabels[task.memory_status] || task.memory_status }}</span>
        </div>
        <p>{{ task.archive_summary || task.prompt }}</p>
        <small>
          {{ new Date(task.deleted_at || task.created_at).toLocaleString() }}
          · {{ task.memory_items_count }} 条记忆
        </small>
        <div class="action-row compact">
          <a class="secondary-button inline-button" :href="`/api/tasks/${task.id}/artifacts`" target="_blank">查看文件清单</a>
          <button v-if="['FAILED', 'NOT_ANALYZED'].includes(task.memory_status)" class="secondary-button" type="button" @click="retryMemory(task)">
            重新整理记忆
          </button>
          <button class="secondary-button" type="button" @click="restore(task)">恢复任务</button>
        </div>
      </article>
    </div>
  </section>
</template>
