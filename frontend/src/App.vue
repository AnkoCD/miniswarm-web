<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showFailToast, showSuccessToast } from 'vant'
import { createProject, listProjects, listTasks } from './api'
import { useAuthStore } from './stores/auth'
import type { Project, Task } from './types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const projects = ref<Project[]>([])
const tasks = ref<Task[]>([])
const leftCollapsed = ref(localStorage.getItem('miniswarm:left-collapsed') === 'true')
const mobileDrawer = ref(false)
const theme = ref<'light' | 'dark'>(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
const projectDialogOpen = ref(false)
const newProjectName = ref('')
const creatingProject = ref(false)
const bare = computed(() => Boolean(route.meta.bare) || !auth.user)

const taskGroups = computed(() => {
  const grouped = new Map<string, Task[]>()
  for (const task of tasks.value) {
    if (!task.project_id) continue
    const current = grouped.get(task.project_id) || []
    if (current.length < 3) current.push(task)
    grouped.set(task.project_id, current)
  }
  return grouped
})

async function refreshNavigation() {
  if (!auth.user || bare.value) return
  try {
    ;[projects.value, tasks.value] = await Promise.all([listProjects(), listTasks()])
  } catch {
    // 页面主体会显示更具体的错误，不重复打扰。
  }
}

function closeMobile() {
  mobileDrawer.value = false
}

function showFiles() {
  window.dispatchEvent(new CustomEvent('miniswarm:show-files'))
}

function toggleLeft() {
  leftCollapsed.value = !leftCollapsed.value
  localStorage.setItem('miniswarm:left-collapsed', String(leftCollapsed.value))
}

function toggleTheme() {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  document.documentElement.dataset.theme = theme.value
  document.documentElement.classList.toggle('van-theme-dark', theme.value === 'dark')
  localStorage.setItem('miniswarm:theme', theme.value)
}

function addProject() {
  newProjectName.value = ''
  projectDialogOpen.value = true
}

async function submitProject() {
  const name = newProjectName.value.trim()
  if (!name) return
  creatingProject.value = true
  try {
    const project = await createProject({ name })
    projectDialogOpen.value = false
    await refreshNavigation()
    await router.push(`/projects/${project.id}`)
    showSuccessToast('项目已创建')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '项目创建失败')
  } finally {
    creatingProject.value = false
  }
}

async function signOut() {
  await auth.logout()
  await router.replace({ name: 'login' })
}

function handleShortcut(event: KeyboardEvent) {
  const mod = event.ctrlKey || event.metaKey
  if (mod && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    router.push('/search')
  } else if (mod && event.key.toLowerCase() === 'n') {
    event.preventDefault()
    router.push('/')
  } else if (mod && event.key.toLowerCase() === 'b' && event.shiftKey) {
    event.preventDefault()
    window.dispatchEvent(new CustomEvent('miniswarm:toggle-right'))
  } else if (mod && event.key.toLowerCase() === 'b') {
    event.preventDefault()
    toggleLeft()
  } else if (event.key === 'Escape') {
    closeMobile()
    window.dispatchEvent(new CustomEvent('miniswarm:escape'))
  }
}

watch(() => route.fullPath, () => {
  closeMobile()
  refreshNavigation()
})

watch(
  () => auth.user?.id,
  () => refreshNavigation(),
  { immediate: true },
)

onMounted(() => {
  window.addEventListener('keydown', handleShortcut)
  window.addEventListener('miniswarm:refresh-navigation', refreshNavigation)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleShortcut)
  window.removeEventListener('miniswarm:refresh-navigation', refreshNavigation)
})
</script>

<template>
  <div v-if="bare" class="legacy-app-shell">
    <RouterView />
  </div>
  <div v-else class="codex-app">
    <button class="mobile-menu-button" type="button" aria-label="打开导航" @click="mobileDrawer = true">☰</button>
    <div v-if="mobileDrawer" class="drawer-backdrop" @click="closeMobile" />
    <aside :class="['workspace-sidebar', { collapsed: leftCollapsed, mobileOpen: mobileDrawer }]">
      <div class="sidebar-brand-row">
        <RouterLink to="/" class="workspace-brand" title="MiniSwarm">
          <span class="brand-mark">M</span>
          <strong v-if="!leftCollapsed">MiniSwarm</strong>
        </RouterLink>
        <button class="icon-button desktop-only" type="button" aria-label="折叠左栏" @click="toggleLeft">
          {{ leftCollapsed ? '›' : '‹' }}
        </button>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <RouterLink to="/" class="nav-item"><span>✎</span><b>新建任务</b></RouterLink>
        <RouterLink to="/queue" class="nav-item">
          <span>◷</span><b>运行队列</b>
          <em v-if="!leftCollapsed">{{ tasks.filter(t => ['QUEUED','RUNNING','WAITING_APPROVAL','PLANNING','REVIEWING'].includes(t.status)).length }}</em>
        </RouterLink>
        <RouterLink to="/search" class="nav-item"><span>⌕</span><b>全局搜索</b><kbd v-if="!leftCollapsed">⌘K</kbd></RouterLink>
        <RouterLink to="/skills" class="nav-item"><span>◇</span><b>Skills</b></RouterLink>
        <RouterLink to="/archived" class="nav-item"><span>▱</span><b>归档任务</b></RouterLink>
        <RouterLink to="/memories" class="nav-item"><span>◎</span><b>全局记忆</b></RouterLink>
      </nav>

      <section v-if="!leftCollapsed" class="project-navigation">
        <div class="sidebar-section-title">
          <span>项目</span>
          <button class="icon-button" type="button" aria-label="创建项目" @click="addProject">＋</button>
        </div>
        <div class="project-tree">
          <div v-for="project in projects" :key="project.id" class="project-tree-item">
            <RouterLink :to="`/projects/${project.id}`" class="project-link">
              <span>▱</span><strong>{{ project.name }}</strong>
              <small>{{ project.current_user_role }}</small>
            </RouterLink>
            <RouterLink
              v-for="task in taskGroups.get(project.id) || []"
              :key="task.id"
              :to="`/tasks/${task.id}`"
              class="recent-task-link"
            >
              <i :class="`task-dot status-${task.status.toLowerCase()}`" />
              <span>{{ task.title }}</span>
            </RouterLink>
          </div>
        </div>
      </section>

      <div class="sidebar-footer">
        <button class="nav-item theme-switch" type="button" @click="toggleTheme">
          <span class="theme-icon" aria-hidden="true">{{ theme === 'dark' ? '☀' : '☾' }}</span>
          <b v-if="!leftCollapsed">{{ theme === 'dark' ? '切换白色界面' : '切换黑色界面' }}</b>
        </button>
        <RouterLink v-if="auth.user?.role === 'admin'" to="/admin" class="nav-item"><span>⚙</span><b>系统管理</b></RouterLink>
        <div class="account-row">
          <span class="account-avatar">{{ auth.user?.username.slice(0, 1).toUpperCase() }}</span>
          <div v-if="!leftCollapsed"><strong>{{ auth.user?.username }}</strong><small>{{ auth.user?.role }}</small></div>
          <button v-if="!leftCollapsed" class="icon-button" type="button" title="退出" @click="signOut">↪</button>
        </div>
      </div>
    </aside>

    <main :class="['workspace-main', { leftCollapsed }]">
      <RouterView :key="route.fullPath" />
    </main>

    <nav class="mobile-bottom-nav" aria-label="手机导航">
      <RouterLink to="/"><span>⌂</span><b>对话</b></RouterLink>
      <RouterLink to="/queue"><span>◷</span><b>进度</b></RouterLink>
      <button type="button" @click="showFiles"><span>▱</span><b>文件</b></button>
      <button type="button" @click="mobileDrawer = true"><span>•••</span><b>更多</b></button>
    </nav>

    <div v-if="projectDialogOpen" class="workspace-modal-backdrop" @click.self="projectDialogOpen = false">
      <form class="workspace-modal" @submit.prevent="submitProject">
        <header><div><strong>创建项目空间</strong><small>任务、文件和项目记忆会集中保存在这里</small></div><button type="button" aria-label="关闭" @click="projectDialogOpen = false">×</button></header>
        <label><span>项目名称</span><input v-model="newProjectName" autofocus maxlength="120" placeholder="例如：产品报告" /></label>
        <footer><button type="button" @click="projectDialogOpen = false">取消</button><button class="primary" type="submit" :disabled="creatingProject || !newProjectName.trim()">{{ creatingProject ? '创建中…' : '创建并打开' }}</button></footer>
      </form>
    </div>
  </div>
</template>
