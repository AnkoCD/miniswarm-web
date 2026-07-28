<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant'
import {
  addProjectMember,
  archiveProject,
  archiveProjectFile,
  getProject,
  getProjectMemories,
  listProjectFiles,
  listProjectMembers,
  listProjectTasks,
  updateProject,
  updateProjectMember,
  uploadProjectFile,
} from '../api'
import type { Project, ProjectFile, ProjectMember, ProjectMemoryBundle, ProjectRole, Task } from '../types'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.id)
const project = ref<Project | null>(null)
const files = ref<ProjectFile[]>([])
const members = ref<ProjectMember[]>([])
const tasks = ref<Task[]>([])
const memories = ref<ProjectMemoryBundle | null>(null)
const loading = ref(true)
const uploading = ref(false)
const dialogMode = ref<'edit' | 'invite' | null>(null)
const editName = ref('')
const editDescription = ref('')
const inviteUsername = ref('')
const inviteRole = ref<ProjectRole>('EDITOR')
const savingDialog = ref(false)
const canEdit = computed(() => ['OWNER', 'EDITOR'].includes(project.value?.current_user_role || ''))
const isOwner = computed(() => project.value?.current_user_role === 'OWNER')

async function load() {
  loading.value = true
  try {
    ;[project.value, files.value, members.value, tasks.value, memories.value] = await Promise.all([
      getProject(projectId),
      listProjectFiles(projectId),
      listProjectMembers(projectId),
      listProjectTasks(projectId),
      getProjectMemories(projectId),
    ])
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '项目加载失败')
  } finally {
    loading.value = false
  }
}

function editProject() {
  if (!project.value) return
  editName.value = project.value.name
  editDescription.value = project.value.description
  dialogMode.value = 'edit'
}

async function saveProjectEdit() {
  const name = editName.value.trim()
  if (!name) return
  savingDialog.value = true
  try {
    project.value = await updateProject(projectId, { name, description: editDescription.value.trim() })
    dialogMode.value = null
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
    showSuccessToast('项目已更新')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '更新失败')
  } finally {
    savingDialog.value = false
  }
}

async function togglePin() {
  if (!project.value) return
  project.value = await updateProject(projectId, { is_pinned: !project.value.is_pinned })
  window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
}

function invite() {
  inviteUsername.value = ''
  inviteRole.value = 'EDITOR'
  dialogMode.value = 'invite'
}

async function submitInvite() {
  const username = inviteUsername.value.trim()
  if (!username) return
  savingDialog.value = true
  try {
    await addProjectMember(projectId, username, inviteRole.value)
    members.value = await listProjectMembers(projectId)
    dialogMode.value = null
    showSuccessToast('成员已加入')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '邀请失败')
  } finally {
    savingDialog.value = false
  }
}

async function changeRole(member: ProjectMember, event: Event) {
  const role = (event.target as HTMLSelectElement).value as ProjectRole
  try {
    await updateProjectMember(projectId, member.user_id, role)
    members.value = await listProjectMembers(projectId)
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '角色更新失败')
  }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  if (!selected.length) return
  uploading.value = true
  try {
    for (const file of selected) await uploadProjectFile(projectId, file)
    files.value = await listProjectFiles(projectId)
    showSuccessToast('项目文件已上传；同名文件会生成新版本')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function archiveFile(item: ProjectFile) {
  try {
    await showConfirmDialog({ title: '归档文件', message: '文件只会从当前列表隐藏，历史版本和磁盘内容都会保留。' })
    await archiveProjectFile(projectId, item.id)
    files.value = await listProjectFiles(projectId)
  } catch (error: any) {
    if (error?.response) showFailToast(error.response.data?.detail || '归档失败')
  }
}

async function archiveCurrentProject() {
  try {
    await showConfirmDialog({ title: '归档项目', message: '项目和全部历史资料会保留，不会永久删除。' })
    await archiveProject(projectId)
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
    await router.replace('/')
  } catch (error: any) {
    if (error?.response) showFailToast(error.response.data?.detail || '归档失败')
  }
}

onMounted(load)
</script>

<template>
  <section v-if="loading" class="content-page workbench-empty">正在加载项目…</section>
  <section v-else-if="project" class="content-page project-page">
    <header class="content-page-header">
      <div><p class="page-kicker">项目空间 · {{ project.current_user_role }}</p><h1>{{ project.name }}</h1><p>{{ project.description || '尚未填写项目说明。' }}</p></div>
      <div class="page-actions">
        <button v-if="canEdit" class="subtle-button" @click="editProject">编辑</button>
        <button class="subtle-button" @click="togglePin">{{ project.is_pinned ? '取消置顶' : '置顶' }}</button>
        <RouterLink class="primary-inline-button" :to="{ path: '/', query: { project: project.id } }">在此项目中新建</RouterLink>
      </div>
    </header>

    <div class="project-summary-grid">
      <article><span>最近任务</span><strong>{{ tasks.length }}</strong><small>{{ tasks[0]?.title || '暂无' }}</small></article>
      <article><span>项目文件</span><strong>{{ files.length }}</strong><small>默认只读引用并生成任务快照</small></article>
      <article><span>项目成员</span><strong>{{ members.length }}</strong><small>私有项目</small></article>
      <article><span>项目记忆</span><strong>{{ memories?.items.length || 0 }}</strong><small>{{ memories?.items.filter(item => item.status === 'CANDIDATE').length || 0 }} 条待确认</small></article>
    </div>

    <section class="content-card">
      <div class="card-heading"><div><h2>项目文件</h2><p>同名上传会自动创建新版本，不覆盖历史文件。</p></div><label v-if="canEdit" class="subtle-button file-upload-button">{{ uploading ? '上传中…' : '上传文件' }}<input type="file" multiple :disabled="uploading" @change="upload" /></label></div>
      <div v-if="!files.length" class="context-placeholder">暂无项目文件</div>
      <div v-else class="data-list">
        <div v-for="item in files" :key="item.id">
          <span class="file-type">{{ item.filename.split('.').pop()?.toUpperCase() }}</span>
          <div><strong>{{ item.filename }}</strong><small>v{{ item.version }} · {{ (item.size / 1024).toFixed(1) }} KB · {{ new Date(item.created_at).toLocaleString() }}</small></div>
          <a class="text-link" :href="`/api/projects/${projectId}/files/${item.id}/download`">下载</a>
          <button v-if="canEdit" class="text-link danger-text" @click="archiveFile(item)">归档</button>
        </div>
      </div>
    </section>

    <div class="two-column-cards">
      <section class="content-card">
        <div class="card-heading"><div><h2>项目记忆</h2><p>与个人全局记忆独立。</p></div></div>
        <p class="memory-profile">{{ memories?.profile.summary || '尚未形成项目记忆。归档任务后会自动整理。' }}</p>
        <div class="memory-mini-list">
          <article v-for="item in memories?.items.slice(0, 8)" :key="item.id"><span>{{ item.category }}</span><p>{{ item.statement }}</p><small>{{ item.status }}</small></article>
        </div>
      </section>
      <section class="content-card">
        <div class="card-heading"><div><h2>成员</h2><p>管理员不会自动获得项目内容权限。</p></div><button v-if="isOwner" class="text-link" @click="invite">邀请</button></div>
        <div class="member-list">
          <div v-for="member in members" :key="member.id">
            <span class="account-avatar">{{ member.username.slice(0, 1).toUpperCase() }}</span>
            <div><strong>{{ member.username }}</strong><small>{{ member.user_id === project.owner_id ? '项目拥有者' : '项目成员' }}</small></div>
            <select v-if="isOwner && member.user_id !== project.owner_id" :value="member.role" @change="changeRole(member, $event)"><option value="EDITOR">EDITOR</option><option value="VIEWER">VIEWER</option></select>
            <span v-else>{{ member.role }}</span>
          </div>
        </div>
      </section>
    </div>

    <section class="content-card">
      <div class="card-heading"><div><h2>最近对话与任务</h2><p>所有成员只看到自己已获授权的项目。</p></div></div>
      <div class="data-list">
        <RouterLink v-for="item in tasks" :key="item.id" :to="`/tasks/${item.id}`">
          <i :class="`task-dot status-${item.status.toLowerCase()}`" />
          <div><strong>{{ item.title }}</strong><small>{{ item.current_step || item.prompt }}</small></div>
          <span>{{ item.status }}</span>
        </RouterLink>
      </div>
    </section>

    <button v-if="isOwner" class="archive-project-button" @click="archiveCurrentProject">软归档此项目</button>
  </section>

  <div v-if="dialogMode" class="workspace-modal-backdrop" @click.self="dialogMode = null">
    <form v-if="dialogMode === 'edit'" class="workspace-modal" @submit.prevent="saveProjectEdit">
      <header><div><strong>编辑项目空间</strong><small>名称和说明会成为 Agent 的项目上下文</small></div><button type="button" aria-label="关闭" @click="dialogMode = null">×</button></header>
      <div class="workspace-modal-fields">
        <label><span>项目名称</span><input v-model="editName" maxlength="120" /></label>
        <label><span>项目说明</span><textarea v-model="editDescription" maxlength="2000" rows="5" placeholder="目标、交付偏好、长期约束…" /></label>
      </div>
      <footer><button type="button" @click="dialogMode = null">取消</button><button class="primary" type="submit" :disabled="savingDialog || !editName.trim()">{{ savingDialog ? '保存中…' : '保存' }}</button></footer>
    </form>
    <form v-else class="workspace-modal" @submit.prevent="submitInvite">
      <header><div><strong>添加项目成员</strong><small>只能添加系统中已经存在的账号</small></div><button type="button" aria-label="关闭" @click="dialogMode = null">×</button></header>
      <div class="workspace-modal-fields">
        <label><span>用户名</span><input v-model="inviteUsername" maxlength="64" autocomplete="off" /></label>
        <label><span>权限</span><select v-model="inviteRole"><option value="EDITOR">可编辑</option><option value="VIEWER">只读</option></select></label>
      </div>
      <footer><button type="button" @click="dialogMode = null">取消</button><button class="primary" type="submit" :disabled="savingDialog || !inviteUsername.trim()">{{ savingDialog ? '添加中…' : '添加成员' }}</button></footer>
    </form>
  </div>
</template>
