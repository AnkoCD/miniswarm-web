<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showFailToast, showSuccessToast } from 'vant'
import { createUser, getSystemConfig, getWorkers, listUsers } from '../api'
import type { SystemConfig, User, WorkerStatus } from '../types'

const users = ref<User[]>([])
const system = ref<SystemConfig | null>(null)
const workers = ref<WorkerStatus[]>([])
const username = ref('')
const password = ref('')
const submitting = ref(false)

async function load() {
  try {
    ;[users.value, system.value, workers.value] = await Promise.all([listUsers(), getSystemConfig(), getWorkers()])
  } catch {
    showFailToast('管理信息加载失败')
  }
}

async function addUser() {
  if (username.value.length < 2 || password.value.length < 12) {
    showFailToast('用户名至少 2 位，密码至少 12 位')
    return
  }
  submitting.value = true
  try {
    await createUser({ username: username.value.trim(), password: password.value, role: 'user' })
    username.value = ''
    password.value = ''
    await load()
    showSuccessToast('账号已创建')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '创建失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <RouterLink to="/" class="back-link">← 返回任务</RouterLink>
    <p class="eyebrow">仅管理员可见</p>
    <h1>系统管理</h1>

    <div v-if="system" class="system-grid">
      <article><span>DeepSeek</span><strong>{{ system.deepseek_configured ? '已配置' : '未配置' }}</strong></article>
      <article><span>AnySearch</span><strong>{{ system.anysearch_configured ? '已配置 Key' : '匿名模式（低限额）' }}</strong></article>
      <article><span>Orchestrator</span><strong>{{ system.model_orchestrator }}</strong></article>
      <article><span>Worker</span><strong>{{ system.model_worker }}</strong></article>
      <article><span>Agent 上限</span><strong>{{ system.max_agents_per_task }} / 任务，{{ system.max_global_agents }} 全局</strong></article>
    </div>

    <div class="section-heading"><h2>账号（{{ users.length }}/{{ system?.max_users || 3 }}）</h2></div>
    <div class="user-list">
      <div v-for="user in users" :key="user.id"><strong>{{ user.username }}</strong><span>{{ user.role }}</span></div>
    </div>

    <div class="section-heading"><h2>Worker 状态</h2><button class="text-button" type="button" @click="load">刷新</button></div>
    <div v-if="workers.length" class="user-list">
      <div v-for="worker in workers" :key="worker.name">
        <strong>{{ worker.name }}</strong>
        <span>{{ worker.online ? '在线' : '离线' }} · 运行 {{ worker.active_tasks }} · 排队 {{ worker.reserved_tasks }}</span>
      </div>
    </div>
    <div v-else class="empty-state">未发现在线 Worker</div>

    <form v-if="users.length < (system?.max_users || 3)" class="admin-form" @submit.prevent="addUser">
      <h2>新增普通账号</h2>
      <label><span>用户名</span><input v-model="username" autocomplete="off" /></label>
      <label><span>初始密码</span><input v-model="password" type="password" autocomplete="new-password" /></label>
      <button class="primary-button" type="submit" :disabled="submitting">创建账号</button>
    </form>

    <p class="security-note">
      DeepSeek 与 AnySearch API Key 只通过服务器 <code>/opt/miniswarm/.env</code> 配置，
      网页仅显示是否已配置，永远不会读取或回显密钥。
    </p>
  </section>
</template>

<style scoped>
h1 { margin-bottom: 24px; font-size: 34px; letter-spacing: -.04em; }
.system-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.system-grid article, .user-list, .admin-form {
  padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface);
}
.system-grid span, .system-grid strong { display: block; }
.system-grid span { margin-bottom: 7px; color: var(--text-muted); font-size: 11px; }
.system-grid strong { font-size: 13px; }
.user-list { padding: 0; overflow: hidden; }
.user-list div { display: flex; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--border-soft); }
.user-list div:last-child { border-bottom: 0; }
.user-list span { color: var(--text-2); font-size: 12px; }
.admin-form { display: grid; gap: 14px; margin-top: 22px; }
.admin-form h2 { margin: 0; font-size: 17px; }
.security-note {
  margin-top: 22px; padding: 14px; border-radius: var(--radius-sm);
  color: var(--text-2); background: var(--surface-sunken); font-size: 13px; line-height: 1.5;
}
@media (max-width: 520px) { .system-grid { grid-template-columns: 1fr; } }
</style>
