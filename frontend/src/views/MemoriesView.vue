<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showFailToast, showSuccessToast } from 'vant'
import { activateMemory, disableMemory, getMemoryProfile, listMemories, updateMemory } from '../api'
import type { UserMemory, UserMemoryProfile } from '../types'

const profile = ref<UserMemoryProfile | null>(null)
const memories = ref<UserMemory[]>([])
const total = ref(0)
const status = ref('')
const category = ref('')
const query = ref('')
const loading = ref(true)

const categoryLabels: Record<string, string> = {
  preference: '明确偏好',
  habit: '使用习惯',
  constraint: '长期约束',
  workflow: '工作流程',
  format: '输出格式',
  correction: '纠错经验',
  project: '项目背景',
}

const statusLabels: Record<string, string> = {
  ACTIVE: '已生效',
  CANDIDATE: '待确认',
  SUPERSEDED: '已替代',
  DISABLED: '已停用',
}

async function refresh() {
  loading.value = true
  try {
    const [profileResult, listResult] = await Promise.all([
      getMemoryProfile(),
      listMemories({
        status: status.value || undefined,
        category: category.value || undefined,
        q: query.value || undefined,
        limit: 500,
      }),
    ])
    profile.value = profileResult
    memories.value = listResult.items
    total.value = listResult.total
  } catch {
    showFailToast('全局记忆加载失败')
  } finally {
    loading.value = false
  }
}

async function activate(item: UserMemory) {
  try {
    await activateMemory(item.id)
    showSuccessToast('记忆已生效')
    await refresh()
  } catch {
    showFailToast('操作失败')
  }
}

async function disable(item: UserMemory) {
  try {
    await disableMemory(item.id)
    showSuccessToast('记忆已停用')
    await refresh()
  } catch {
    showFailToast('操作失败')
  }
}

async function edit(item: UserMemory) {
  const statement = window.prompt('修改这条全局记忆', item.statement)?.trim()
  if (!statement || statement === item.statement) return
  try {
    await updateMemory(item.id, { statement })
    showSuccessToast('记忆已更新')
    await refresh()
  } catch {
    showFailToast('修改失败')
  }
}

onMounted(refresh)
</script>

<template>
  <section>
    <div class="hero-copy">
      <p class="eyebrow">跨任务偏好</p>
      <h1>全局记忆</h1>
      <p class="muted">只在当前账号内生效；当前任务的明确指令始终优先。</p>
    </div>

    <article class="prompt-card profile-card">
      <div class="section-heading">
        <h2>我的使用习惯</h2>
        <small v-if="profile" class="muted">版本 {{ profile.version }} · {{ new Date(profile.updated_at).toLocaleString() }}</small>
      </div>
      <p>{{ profile?.summary || '尚未形成全局记忆。归档任务后会自动整理。' }}</p>
    </article>

    <div class="filter-bar">
      <input v-model="query" placeholder="搜索记忆" @keyup.enter="refresh" />
      <select v-model="category" @change="refresh">
        <option value="">全部类别</option>
        <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
      </select>
      <select v-model="status" @change="refresh">
        <option value="">全部状态</option>
        <option value="ACTIVE">已生效</option>
        <option value="CANDIDATE">待确认</option>
        <option value="DISABLED">已停用</option>
        <option value="SUPERSEDED">已替代</option>
      </select>
      <button class="secondary-button" type="button" @click="refresh">查询</button>
    </div>

    <div class="section-heading">
      <h2>记忆条目</h2>
      <span class="muted">共 {{ total }} 条</span>
    </div>
    <div v-if="loading" class="empty-state">正在加载…</div>
    <div v-else-if="!memories.length" class="empty-state">没有符合条件的记忆</div>
    <div v-else class="memory-list">
      <article v-for="item in memories" :key="item.id" class="memory-card">
        <div class="memory-card-head">
          <div>
            <span class="memory-category">{{ categoryLabels[item.category] || item.category }}</span>
            <strong>{{ statusLabels[item.status] || item.status }}</strong>
          </div>
          <small>可信度 {{ Math.round(item.confidence * 100) }}% · 出现 {{ item.occurrence_count }} 次</small>
        </div>
        <p>{{ item.statement }}</p>
        <small class="muted">最近出现：{{ new Date(item.last_seen_at).toLocaleString() }}</small>
        <div class="action-row compact">
          <button class="secondary-button" type="button" @click="edit(item)">修改</button>
          <button v-if="item.status !== 'ACTIVE'" class="secondary-button" type="button" @click="activate(item)">设为生效</button>
          <button v-if="item.status !== 'DISABLED'" class="secondary-button danger" type="button" @click="disable(item)">停用</button>
        </div>
      </article>
    </div>
  </section>
</template>
