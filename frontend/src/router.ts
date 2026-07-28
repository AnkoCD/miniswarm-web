import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import LoginView from './views/LoginView.vue'
import TaskDetailView from './views/TaskDetailView.vue'
import TasksView from './views/TasksView.vue'
import AdminView from './views/AdminView.vue'
import ArchivedTasksView from './views/ArchivedTasksView.vue'
import MemoriesView from './views/MemoriesView.vue'
import WorkbenchView from './views/WorkbenchView.vue'
import ProjectView from './views/ProjectView.vue'
import SearchView from './views/SearchView.vue'
import SkillsView from './views/SkillsView.vue'
import QueueView from './views/QueueView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true, bare: true } },
    { path: '/', name: 'tasks', component: WorkbenchView },
    { path: '/tasks/:id', name: 'task-detail', component: WorkbenchView },
    { path: '/projects/:id', name: 'project', component: ProjectView },
    { path: '/search', name: 'search', component: SearchView },
    { path: '/skills', name: 'skills', component: SkillsView },
    { path: '/queue', name: 'queue', component: QueueView },
    { path: '/archived', name: 'archived', component: ArchivedTasksView },
    { path: '/memories', name: 'memories', component: MemoriesView },
    { path: '/admin', name: 'admin', component: AdminView, meta: { admin: true } },
    { path: '/legacy', name: 'legacy', component: TasksView, meta: { bare: true } },
    { path: '/legacy/tasks/:id', name: 'legacy-task-detail', component: TaskDetailView, meta: { bare: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()
  if (!to.meta.public && !auth.user) return { name: 'login', query: { next: to.fullPath } }
  if (to.meta.admin && auth.user?.role !== 'admin') return { name: 'tasks' }
  if (to.name === 'login' && auth.user) return { name: 'tasks' }
  return true
})
