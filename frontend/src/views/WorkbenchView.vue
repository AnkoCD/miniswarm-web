<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant'
import {
  archiveTask,
  cancelTask,
  createTask,
  decideApproval,
  apiErrorMessage,
  getEvents,
  getMe,
  getTask,
  getUsage,
  listApprovals,
  listArtifacts,
  listProjectFiles,
  listProjects,
  listSkills,
  listTaskMessages,
  listTaskNodes,
  listTaskSources,
  listToolCalls,
  sendTaskMessage,
  redirectToLogin,
  retryTask,
  startChat,
  startTask,
  uploadTaskFile,
} from '../api'
import ArtifactPreview from '../components/ArtifactPreview.vue'
import MarkdownContent from '../components/MarkdownContent.vue'
import type {
  Approval,
  Artifact,
  Project,
  ProjectFile,
  Skill,
  Task,
  TaskEvent,
  TaskMessage,
  TaskNode,
  TaskSource,
  ToolCall,
  UsageSummary,
} from '../types'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.id ? String(route.params.id) : '')
const task = ref<Task | null>(null)
const projects = ref<Project[]>([])
const projectFiles = ref<ProjectFile[]>([])
const selectedProjectId = ref('')
const selectedProjectFiles = ref<string[]>([])
const skills = ref<Skill[]>([])
const selectedSkills = ref<string[]>([])
const skillMode = ref<'auto' | 'manual' | 'off'>('auto')
const mode = ref<'chat' | 'task' | 'revise'>('chat')
const prompt = ref('')
const attachments = ref<File[]>([])
const modelMode = ref('auto')
const executionMode = ref('standard')
const autonomyMode = ref('safe')
const taskType = ref('auto')
const settingsOpen = ref(false)
const submitting = ref(false)
const loading = ref(true)
const rightOpen = ref(localStorage.getItem('miniswarm:right-open') !== 'false')
const mobileContextOpen = ref(false)
const activeTab = ref<'conversation' | 'file'>('conversation')
const previewArtifact = ref<Artifact | null>(null)
const messages = ref<TaskMessage[]>([])
const events = ref<TaskEvent[]>([])
const artifacts = ref<Artifact[]>([])
const approvals = ref<Approval[]>([])
const nodes = ref<TaskNode[]>([])
const toolCalls = ref<ToolCall[]>([])
const sources = ref<TaskSource[]>([])
const usage = ref<UsageSummary | null>(null)
const loadError = ref('')
const messageList = ref<HTMLElement | null>(null)
const autoFollow = ref(true)
const uploadDone = ref(0)
const uploadTotal = ref(0)
let stream: EventSource | null = null
let refreshTimer: ReturnType<typeof setTimeout> | null = null
let refreshInFlight = false
const pendingRefresh = new Set<RefreshSection>()

type RefreshSection = 'task' | 'messages' | 'artifacts' | 'approvals' | 'nodes' | 'tools' | 'sources' | 'usage'

const terminal = computed(() => Boolean(task.value && ['SUCCEEDED', 'FAILED', 'CANCELED'].includes(task.value.status)))
const running = computed(() => Boolean(task.value && !['CREATED', 'SUCCEEDED', 'FAILED', 'CANCELED'].includes(task.value.status)))
const canWrite = computed(() => {
  const project = projects.value.find(item => item.id === (task.value?.project_id || selectedProjectId.value))
  return Boolean(project && project.current_user_role !== 'VIEWER')
})
const currentProject = computed(() => projects.value.find(item => item.id === (task.value?.project_id || selectedProjectId.value)))
const pendingApprovals = computed(() => approvals.value.filter(item => item.status === 'PENDING'))
const finalArtifacts = computed(() => artifacts.value.filter(item => item.is_final))
const activeAgentCount = computed(() => nodes.value.filter(item => ['READY', 'QUEUED', 'RUNNING', 'WAITING'].includes(item.status)).length)
const executionEvents = computed(() => events.value.filter(item => !item.event_type.startsWith('message.')).slice(-30))
const isWebDesignTask = computed(() => {
  const text = `${task.value?.title || ''} ${task.value?.prompt || prompt.value}`.toLowerCase()
  return /(网页|网站|前端|界面|ui|ux|website|frontend|web design)/i.test(text)
})
const draftKey = computed(() => `miniswarm:composer-draft:${taskId.value || 'new'}`)
const attachmentTotalSize = computed(() => attachments.value.reduce((sum, file) => sum + file.size, 0))

const statusLabel: Record<string, string> = {
  CREATED: '对话', QUEUED: '排队中', PLANNING: '规划中', RUNNING: '执行中',
  WAITING_APPROVAL: '等待审批', REVIEWING: '审查中', REWORKING: '返工中',
  PACKAGING: '交付中', SUCCEEDED: '已完成', FAILED: '失败', CANCELING: '取消中', CANCELED: '已取消',
}

function uuid() {
  return crypto.randomUUID()
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: value >= 10_000 ? 'compact' : 'standard' }).format(value)
}

function isNearBottom() {
  const element = messageList.value
  if (!element) return true
  return element.scrollHeight - element.scrollTop - element.clientHeight < 140
}

function trackScroll() {
  autoFollow.value = isNearBottom()
}

function scrollToLatest(force = false) {
  if (!force && !autoFollow.value) return
  nextTick(() => {
    messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: force ? 'smooth' : 'auto' })
    autoFollow.value = true
  })
}

function restoreComposerState() {
  try {
    const preferences = JSON.parse(localStorage.getItem('miniswarm:composer-preferences') || '{}')
    modelMode.value = preferences.modelMode || modelMode.value
    executionMode.value = preferences.executionMode || executionMode.value
    autonomyMode.value = preferences.autonomyMode || autonomyMode.value
    taskType.value = preferences.taskType || taskType.value
    skillMode.value = preferences.skillMode || skillMode.value
    const installed = new Set(skills.value.map(item => item.name))
    selectedSkills.value = Array.isArray(preferences.selectedSkills)
      ? preferences.selectedSkills.filter((name: unknown) => typeof name === 'string' && installed.has(name))
      : selectedSkills.value
  } catch {
    // 无效的本地偏好直接忽略。
  }
  if (!prompt.value) prompt.value = localStorage.getItem(draftKey.value) || ''
}

function toggleRight() {
  rightOpen.value = !rightOpen.value
  localStorage.setItem('miniswarm:right-open', String(rightOpen.value))
}

function showPreview(artifact: Artifact) {
  previewArtifact.value = artifact
  activeTab.value = 'file'
  mobileContextOpen.value = false
}

function closePreview() {
  activeTab.value = 'conversation'
  previewArtifact.value = null
}

async function loadProjectFiles() {
  if (!selectedProjectId.value) {
    projectFiles.value = []
    return
  }
  try {
    projectFiles.value = await listProjectFiles(selectedProjectId.value)
  } catch {
    projectFiles.value = []
  }
}

async function loadTaskData(reconnect = true, scrollToEnd = reconnect) {
  if (!taskId.value) return
  const [taskValue, messageValues, eventValues, artifactValues, approvalValues, nodeValues, toolValues, sourceValues, usageValue] = await Promise.all([
    getTask(taskId.value),
    listTaskMessages(taskId.value),
    getEvents(taskId.value),
    listArtifacts(taskId.value),
    listApprovals(taskId.value),
    listTaskNodes(taskId.value),
    listToolCalls(taskId.value),
    listTaskSources(taskId.value),
    getUsage(taskId.value),
  ])
  task.value = taskValue
  selectedProjectId.value = taskValue.project_id || ''
  messages.value = messageValues
  events.value = eventValues
  artifacts.value = artifactValues
  approvals.value = approvalValues
  nodes.value = nodeValues
  toolCalls.value = toolValues
  sources.value = sourceValues
  usage.value = usageValue
  mode.value = terminal.value ? 'chat' : (taskValue.execution_kind === 'chat' ? 'chat' : 'chat')
  if (reconnect) connectStream()
  if (scrollToEnd) scrollToLatest(true)
}

async function initialize() {
  loading.value = true
  loadError.value = ''
  try {
    ;[projects.value, skills.value] = await Promise.all([listProjects(), listSkills()])
    if (taskId.value) {
      await loadTaskData()
    } else {
      task.value = null
      const preferredProject = String(route.query.project || '') || localStorage.getItem('miniswarm:last-project') || ''
      const writableProjects = projects.value.filter(project => project.current_user_role !== 'VIEWER')
      selectedProjectId.value = writableProjects.some(project => project.id === preferredProject)
        ? preferredProject
        : writableProjects[0]?.id || ''
      await loadProjectFiles()
    }
    restoreComposerState()
  } catch (error: any) {
    if (error?.response?.status === 401) {
      redirectToLogin()
      return
    }
    loadError.value = error?.response?.data?.detail || '工作台加载失败，请重试'
    showFailToast(loadError.value)
  } finally {
    loading.value = false
  }
}

function sectionsForEvent(name: string): RefreshSection[] {
  if (name.startsWith('artifact.') || name === 'file.uploaded') return ['task', 'artifacts']
  if (name.startsWith('approval.')) return ['task', 'approvals', 'nodes']
  if (name.startsWith('tool.')) return ['task', 'tools', 'sources']
  if (name.startsWith('message.')) return name === 'message.completed' ? ['messages', 'usage'] : ['messages']
  if (name === 'task.completed' || name === 'task.failed' || name === 'task.canceled') {
    return ['task', 'messages', 'artifacts', 'approvals', 'nodes', 'tools', 'sources', 'usage']
  }
  return ['task', 'nodes', 'usage']
}

async function refreshSections(sections: Set<RefreshSection>) {
  if (!taskId.value) return
  const jobs: Promise<void>[] = []
  if (sections.has('task')) jobs.push(getTask(taskId.value).then(value => { task.value = value }))
  if (sections.has('messages')) jobs.push(listTaskMessages(taskId.value).then(value => { messages.value = value }))
  if (sections.has('artifacts')) jobs.push(listArtifacts(taskId.value).then(value => { artifacts.value = value }))
  if (sections.has('approvals')) jobs.push(listApprovals(taskId.value).then(value => { approvals.value = value }))
  if (sections.has('nodes')) jobs.push(listTaskNodes(taskId.value).then(value => { nodes.value = value }))
  if (sections.has('tools')) jobs.push(listToolCalls(taskId.value).then(value => { toolCalls.value = value }))
  if (sections.has('sources')) jobs.push(listTaskSources(taskId.value).then(value => { sources.value = value }))
  if (sections.has('usage')) jobs.push(getUsage(taskId.value).then(value => { usage.value = value }))
  await Promise.all(jobs)
}

function armRefreshTimer() {
  if (refreshTimer || refreshInFlight) return
  refreshTimer = setTimeout(async () => {
    refreshTimer = null
    if (refreshInFlight || !pendingRefresh.size) return
    const sections = new Set(pendingRefresh)
    pendingRefresh.clear()
    refreshInFlight = true
    try {
      await refreshSections(sections)
    } catch {
      // 下一条事件会再次刷新。
    } finally {
      refreshInFlight = false
      if (pendingRefresh.size) armRefreshTimer()
    }
  }, 550)
}

function scheduleRefresh(eventName: string) {
  for (const section of sectionsForEvent(eventName)) pendingRefresh.add(section)
  armRefreshTimer()
}

function applyStreamMessage(type: string, raw: any) {
  const messageId = raw.message_id || (type === 'message.started' ? raw.content : null)
  if (!messageId) return
  let message = messages.value.find(item => item.id === messageId)
  if (!message) {
    message = {
      id: messageId,
      task_id: taskId.value,
      revision: task.value?.current_revision || 0,
      role: 'assistant',
      mode: 'chat',
      content: '',
      author_user_id: null,
      status: 'STREAMING',
      client_message_id: null,
      created_at: new Date().toISOString(),
    }
    messages.value.push(message)
  }
  if (type === 'message.delta') message.content += raw.delta || ''
  if (type === 'message.completed') {
    message.content = raw.content || message.content
    message.status = 'COMPLETED'
  }
  if (type === 'message.failed') {
    message.status = 'FAILED'
    if (!message.content) message.content = `回复失败：${raw.error || '未知错误'}`
  }
  scrollToLatest()
}

function connectStream() {
  stream?.close()
  if (!taskId.value) return
  const lastId = events.value.at(-1)?.id || 0
  stream = new EventSource(`/api/tasks/${taskId.value}/stream?last_event_id=${lastId}`, { withCredentials: true })
  const names = [
    'task.created', 'task.queued', 'task.planning', 'plan.created', 'task.reviewing', 'task.reworking',
    'task.packaging', 'task.completed', 'task.failed', 'task.canceling', 'task.canceled',
    'agent.created', 'agent.queued', 'agent.started', 'agent.progress', 'agent.completed', 'agent.failed',
    'tool.started', 'tool.completed', 'tool.failed', 'artifact.created', 'artifact.updated', 'file.uploaded',
    'delivery.blocked',
    'approval.required', 'approval.approved', 'approval.denied', 'approval.auto_approved',
    'message.started', 'message.delta', 'message.completed', 'message.failed', 'message.user',
  ]
  for (const name of names) {
    stream.addEventListener(name, event => {
      const raw = JSON.parse((event as MessageEvent).data)
      if (name.startsWith('message.')) applyStreamMessage(name, raw)
      if (raw.id && !events.value.some(item => item.id === raw.id)) {
        events.value.push({ ...raw, event_type: raw.type })
      }
      if (!name.startsWith('message.delta')) scheduleRefresh(name)
    })
  }
  stream.onerror = async () => {
    try {
      await getMe()
    } catch {
      stream?.close()
      redirectToLogin()
    }
  }
}

async function submit() {
  try {
    await getMe()
  } catch {
    redirectToLogin()
    return
  }
  const content = prompt.value.trim()
  if (!content) return showFailToast('请输入内容')
  if (!task.value && !selectedProjectId.value) {
    await initialize()
    if (!selectedProjectId.value) return showFailToast('没有可写项目，请刷新页面或让项目所有者授予编辑权限')
  }
  if (skillMode.value === 'manual' && !selectedSkills.value.length) return showFailToast('请至少选择一个 Skill')
  if (mode.value === 'revise' && !terminal.value) return showFailToast('任务结束后才能修改文件')
  submitting.value = true
  try {
    if (task.value) {
      await sendTaskMessage(task.value.id, content, mode.value, uuid())
      prompt.value = ''
      await loadTaskData(false)
      if (mode.value === 'task') mode.value = 'chat'
    } else {
      const execute = mode.value === 'task'
      const hasUploads = attachments.value.length > 0
      const created = await createTask({
        prompt: content,
        title: content.split('\n')[0].slice(0, 80),
        project_id: selectedProjectId.value,
        project_file_ids: selectedProjectFiles.value,
        execution_kind: execute ? 'task' : 'chat',
        client_request_id: uuid(),
        task_type: taskType.value,
        model_mode: modelMode.value,
        execution_mode: executionMode.value,
        autonomy_mode: autonomyMode.value,
        skill_mode: skillMode.value,
        selected_skills: selectedSkills.value,
        start_immediately: !hasUploads,
      })
      uploadDone.value = 0
      uploadTotal.value = attachments.value.length
      for (let index = 0; index < attachments.value.length; index += 3) {
        const batch = attachments.value.slice(index, index + 3)
        await Promise.all(batch.map(async file => {
          await uploadTaskFile(created.id, file)
          uploadDone.value += 1
        }))
      }
      if (hasUploads) {
        if (execute) await startTask(created.id)
        else await startChat(created.id)
      }
      localStorage.setItem('miniswarm:last-project', selectedProjectId.value)
      localStorage.removeItem(draftKey.value)
      attachments.value = []
      window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
      await router.replace(`/tasks/${created.id}`)
    }
  } catch (error: any) {
    showFailToast(apiErrorMessage(error, '发送失败'))
  } finally {
    submitting.value = false
    uploadDone.value = 0
    uploadTotal.value = 0
  }
}

function chooseAttachments(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  const oversized = files.find(file => file.size > 100 * 1024 * 1024)
  if (oversized) {
    showFailToast(`${oversized.name} 超过 100 MB`)
    input.value = ''
    return
  }
  const combined = [...attachments.value]
  for (const file of files) {
    const duplicate = combined.some(item => (
      item.name === file.name && item.size === file.size && item.lastModified === file.lastModified
    ))
    if (!duplicate) combined.push(file)
  }
  if (combined.length > 20) {
    showFailToast('单次最多添加 20 个附件')
    input.value = ''
    return
  }
  attachments.value = combined
  input.value = ''
}

function removeAttachment(index: number) {
  attachments.value.splice(index, 1)
}

async function approve(item: Approval, decision: 'deny' | 'allow_once' | 'allow_for_task') {
  try {
    await decideApproval(taskId.value, item.id, decision)
    approvals.value = await listApprovals(taskId.value)
    showSuccessToast(decision === 'deny' ? '已拒绝' : '已批准')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '审批失败')
  }
}

async function requestCancel() {
  if (!task.value) return
  try {
    task.value = await cancelTask(task.value.id)
    showSuccessToast('已请求取消')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '取消失败')
  }
}

async function retryCurrent() {
  if (!task.value || !['FAILED', 'CANCELED'].includes(task.value.status)) return
  try {
    task.value = await retryTask(task.value.id)
    showSuccessToast('任务已重新进入队列')
    await loadTaskData(false, false)
    connectStream()
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '重试失败')
  }
}

async function archiveCurrent() {
  if (!task.value) return
  try {
    await showConfirmDialog({
      title: '归档任务',
      message: '任务与文件会保留，并自动分析个人记忆和项目记忆。',
      confirmButtonText: '归档',
    })
    await archiveTask(task.value.id)
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
    await router.replace('/')
  } catch (error: any) {
    if (error?.response) showFailToast(error.response.data?.detail || '归档失败')
  }
}

function handleComposerKey(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    if (!submitting.value) submit()
  }
}

function openFilesOnMobile() {
  mobileContextOpen.value = true
  setTimeout(() => document.querySelector('#context-files')?.scrollIntoView({ behavior: 'smooth' }), 50)
}

function escapePanels() {
  mobileContextOpen.value = false
  closePreview()
}

watch(prompt, value => {
  if (value) localStorage.setItem(draftKey.value, value)
  else localStorage.removeItem(draftKey.value)
})

watch([modelMode, executionMode, autonomyMode, taskType, skillMode, selectedSkills], () => {
  localStorage.setItem('miniswarm:composer-preferences', JSON.stringify({
    modelMode: modelMode.value,
    executionMode: executionMode.value,
    autonomyMode: autonomyMode.value,
    taskType: taskType.value,
    skillMode: skillMode.value,
    selectedSkills: selectedSkills.value,
  }))
}, { deep: true })

onMounted(() => {
  initialize()
  window.addEventListener('miniswarm:toggle-right', toggleRight)
  window.addEventListener('miniswarm:show-files', openFilesOnMobile)
  window.addEventListener('miniswarm:escape', escapePanels)
})
onBeforeUnmount(() => {
  stream?.close()
  if (refreshTimer) clearTimeout(refreshTimer)
  window.removeEventListener('miniswarm:toggle-right', toggleRight)
  window.removeEventListener('miniswarm:show-files', openFilesOnMobile)
  window.removeEventListener('miniswarm:escape', escapePanels)
})
</script>

<template>
  <section v-if="loading" class="workbench-empty">正在打开工作台…</section>
  <section v-else-if="loadError" class="workbench-empty">
    <div class="workspace-error">
      <strong>工作台加载失败</strong>
      <p>{{ loadError }}</p>
      <button class="primary-inline-button" type="button" @click="initialize">重新加载</button>
    </div>
  </section>
  <section v-else :class="['workbench-layout', { 'web-design-task': isWebDesignTask }]">
    <div class="conversation-column">
      <header class="workbench-header">
        <div class="header-identity">
          <span class="project-breadcrumb">{{ currentProject?.name || '选择项目' }}</span>
          <strong>{{ task?.title || '新建任务' }}</strong>
        </div>
        <div class="header-status">
          <span v-if="task" :class="['status-pill', `status-${task.status.toLowerCase()}`]">{{ statusLabel[task.status] }}</span>
          <span v-if="task">{{ task.model_mode === 'auto' ? '自动模型' : task.model_mode }}</span>
          <span v-if="task">{{ task.execution_mode === 'deep' ? '深度思考' : '标准' }}</span>
          <span v-if="task" :class="{ yolo: task.autonomy_mode === 'yolo' }">{{ task.autonomy_mode === 'yolo' ? 'YOLO' : '安全' }}</span>
          <button v-if="task && ['FAILED', 'CANCELED'].includes(task.status)" class="header-action-button" type="button" @click="retryCurrent">重试</button>
          <RouterLink v-if="task" class="header-action-button" to="/">新任务</RouterLink>
          <button class="icon-button" type="button" :aria-label="rightOpen ? '收起上下文栏' : '打开上下文栏'" @click="toggleRight">☷</button>
        </div>
      </header>

      <div v-if="activeTab === 'conversation'" ref="messageList" class="conversation-scroll" @scroll.passive="trackScroll">
        <div v-if="!task" class="new-workspace-hero">
          <div class="hero-orb">M</div>
          <h1>今天想完成什么？</h1>
          <p>选择一个项目，然后聊天、执行任务或基于已有文件继续修改。</p>
          <div class="capability-grid">
            <button type="button" @click="prompt = '分析项目资料并整理关键结论'; mode = 'task'"><span>⌕</span><strong>分析资料</strong><small>并行读取与验证</small></button>
            <button type="button" @click="prompt = '根据项目资料制作一份演示文稿'; mode = 'task'"><span>▣</span><strong>制作文件</strong><small>PPT、Word、PDF、Excel</small></button>
            <button type="button" @click="prompt = '检查现有代码并给出改进建议'; mode = 'task'"><span>⌘</span><strong>代码任务</strong><small>生成、修改、测试</small></button>
          </div>
        </div>

        <template v-else>
          <article v-if="task.status === 'FAILED'" class="task-error-card">
            <div><strong>本轮任务未完成</strong><p>{{ task.error_message || '执行过程中发生错误，可直接重试或补充要求。' }}</p></div>
            <button type="button" @click="retryCurrent">重新执行</button>
          </article>
          <article v-for="message in messages" :key="message.id" :class="['conversation-message', message.role]">
            <div class="message-avatar">{{ message.role === 'user' ? '你' : 'M' }}</div>
            <div class="message-body">
              <header>
                <strong>{{ message.role === 'user' ? '你' : 'MiniSwarm' }}</strong>
                <span v-if="message.mode === 'revise'">修改文件</span>
                <time>{{ new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</time>
              </header>
              <MarkdownContent :content="message.content" />
              <div v-if="message.status === 'STREAMING'" class="streaming-cursor" aria-label="正在生成" />
              <span v-if="message.status === 'FAILED'" class="message-error">生成失败</span>
            </div>
          </article>

          <details v-if="executionEvents.length" class="run-record" open>
            <summary>
              <span>运行记录</span>
              <strong>{{ task?.progress || 0 }}%</strong>
              <small>{{ activeAgentCount }} 个 Agent 活跃 · {{ task?.current_step || '等待中' }}</small>
            </summary>
            <ol>
              <li v-for="event in executionEvents.slice(-10)" :key="event.id">
                <i /><div><strong>{{ event.title }}</strong><small>{{ event.content }}</small></div>
              </li>
            </ol>
          </details>

          <article v-for="approval in pendingApprovals" :key="approval.id" class="inline-approval">
            <span>需要你的批准</span>
            <strong>{{ approval.summary }}</strong>
            <div>
              <button type="button" @click="approve(approval, 'deny')">拒绝</button>
              <button type="button" @click="approve(approval, 'allow_once')">允许一次</button>
              <button type="button" @click="approve(approval, 'allow_for_task')">本任务允许</button>
            </div>
          </article>

          <div v-if="finalArtifacts.length" class="inline-artifacts">
            <button v-for="artifact in finalArtifacts" :key="artifact.id" type="button" @click="showPreview(artifact)">
              <span>▱</span><div><strong>{{ artifact.filename }}</strong><small>{{ formatSize(artifact.size) }}</small></div><em>{{ artifact.inspection_status === 'VERIFIED' ? '已验证' : '预览' }}</em>
            </button>
          </div>
        </template>
      </div>

      <ArtifactPreview
        v-else-if="previewArtifact"
        :task-id="taskId"
        :artifact="previewArtifact"
        @close="closePreview"
      />

      <button v-if="task && activeTab === 'conversation' && !autoFollow" class="jump-latest-button" type="button" @click="scrollToLatest(true)">
        回到最新消息 ↓
      </button>

      <footer class="composer-dock">
        <form class="workbench-composer" @submit.prevent="submit">
          <div v-if="!task" class="project-select-row">
            <select v-model="selectedProjectId" @change="loadProjectFiles">
              <option value="" disabled>选择项目</option>
              <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
            </select>
            <span>{{ currentProject?.current_user_role || '未选择' }}</span>
          </div>
          <textarea
            v-model="prompt"
            maxlength="20000"
            :disabled="submitting || !canWrite"
            :placeholder="canWrite ? '要求后续变更…（Enter 发送，Shift+Enter 换行）' : '当前项目为只读权限'"
            @keydown="handleComposerKey"
          />
          <div v-if="attachments.length || selectedProjectFiles.length" class="attachment-chips">
            <span v-for="(file, index) in attachments" :key="`${file.name}-${file.lastModified}`">{{ file.name }}<button type="button" aria-label="移除附件" @click="removeAttachment(index)">×</button></span>
            <span v-for="fileId in selectedProjectFiles" :key="fileId">{{ projectFiles.find(item => item.id === fileId)?.filename }}</span>
            <small v-if="attachments.length">{{ attachments.length }} 个本地附件 · {{ formatSize(attachmentTotalSize) }}</small>
          </div>
          <div v-if="settingsOpen" class="composer-settings">
            <label><span>模型</span><select v-model="modelMode"><option value="auto">自动</option><option value="deepseek-v4-pro">V4 Pro</option><option value="deepseek-v4-flash">V4 Flash</option></select></label>
            <label><span>思考</span><select v-model="executionMode"><option value="standard">标准</option><option value="deep">深度思考</option></select></label>
            <label><span>安全</span><select v-model="autonomyMode"><option value="safe">安全审批</option><option value="yolo">YOLO（仅本任务）</option></select></label>
            <label><span>任务类型</span><select v-model="taskType"><option value="auto">自动</option><option value="document">文档</option><option value="code">代码</option><option value="data">数据</option><option value="file">文件</option></select></label>
            <label><span>Skills</span><select v-model="skillMode"><option value="auto">自主判断</option><option value="manual">仅选中项</option><option value="off">关闭</option></select></label>
            <div v-if="skillMode !== 'off'" class="compact-skill-list">
              <label v-for="skill in skills" :key="skill.name"><input v-model="selectedSkills" type="checkbox" :value="skill.name" /><span>{{ skill.display_name }}</span></label>
            </div>
            <div v-if="!task && projectFiles.length" class="project-file-picker">
              <strong>引用项目文件</strong>
              <label v-for="file in projectFiles" :key="file.id"><input v-model="selectedProjectFiles" type="checkbox" :value="file.id" /><span>{{ file.filename }} · v{{ file.version }}</span></label>
            </div>
          </div>
          <div class="composer-toolbar">
            <div class="composer-left-actions">
              <label class="icon-button attach-button" title="添加附件">＋<input type="file" multiple @change="chooseAttachments" /></label>
              <button class="icon-button" type="button" title="设置" @click="settingsOpen = !settingsOpen">⌘</button>
              <span v-if="selectedSkills.length" class="skill-count">{{ selectedSkills.length }} Skills</span>
            </div>
            <div class="mode-switch" role="radiogroup" aria-label="输入模式">
              <button type="button" :class="{ active: mode === 'chat' }" @click="mode = 'chat'">聊天</button>
              <button type="button" :class="{ active: mode === 'task' }" :disabled="running || Boolean(task && task.execution_kind !== 'chat')" @click="mode = 'task'">执行任务</button>
              <button type="button" :class="{ active: mode === 'revise' }" :disabled="!terminal" @click="mode = 'revise'">修改文件</button>
            </div>
            <button v-if="running" class="cancel-generation" type="button" @click="requestCancel">停止</button>
            <span v-if="submitting && uploadTotal" class="upload-progress">上传 {{ uploadDone }}/{{ uploadTotal }}</span>
            <button v-if="!running" class="send-button" type="submit" :disabled="submitting || !prompt.trim() || !canWrite" :aria-label="submitting ? '正在发送' : '发送'">{{ submitting ? '…' : '↑' }}</button>
          </div>
        </form>
        <small v-if="autonomyMode === 'yolo' && !task" class="yolo-warning">YOLO 仅对当前任务生效，删除、越界路径和宿主机操作仍会拦截。</small>
      </footer>
    </div>

    <div v-if="mobileContextOpen" class="drawer-backdrop" @click="mobileContextOpen = false" />
    <aside :class="['context-sidebar', { hidden: !rightOpen, mobileOpen: mobileContextOpen }]">
      <header><strong>上下文</strong><button class="icon-button" type="button" @click="mobileContextOpen = false; rightOpen = false">×</button></header>
      <div v-if="!task" class="context-empty">
        <span>☷</span><strong>任务上下文将在这里出现</strong><p>计划、Agents、文件、来源、审批和用量会实时更新。</p>
      </div>
      <template v-else>
        <details v-if="pendingApprovals.length" class="context-section approval-section" open>
          <summary>待审批 <em>{{ pendingApprovals.length }}</em></summary>
          <article v-for="item in pendingApprovals" :key="item.id">
            <strong>{{ item.operation }}</strong><p>{{ item.summary }}</p>
            <div><button @click="approve(item, 'deny')">拒绝</button><button @click="approve(item, 'allow_once')">允许</button></div>
          </article>
        </details>
        <details class="context-section" open>
          <summary>计划 <em>{{ nodes.length }}</em></summary>
          <div v-if="!nodes.length" class="context-placeholder">等待生成执行计划</div>
          <div v-for="node in nodes" :key="node.id" class="plan-node">
            <i :class="`node-${node.status.toLowerCase()}`" />
            <div><strong>{{ node.title }}</strong><small>{{ node.role }} · 权重 {{ node.weight }} · {{ node.status }}</small></div>
          </div>
        </details>
        <details class="context-section" open>
          <summary>Agents <em>{{ nodes.length }}</em></summary>
          <div v-for="node in nodes" :key="`agent-${node.id}`" class="agent-row">
            <span>{{ node.role.slice(0, 1).toUpperCase() }}</span>
            <div><strong>{{ node.role }}</strong><small>{{ node.status }} · 尝试 {{ node.attempt }}</small></div>
          </div>
        </details>
        <details id="context-files" class="context-section" open>
          <summary>输出 <em>{{ artifacts.length }}</em></summary>
          <button v-for="artifact in artifacts" :key="artifact.id" class="context-file" type="button" @click="showPreview(artifact)">
            <span>▱</span><div><strong>{{ artifact.filename }}</strong><small>{{ formatSize(artifact.size) }} · {{ artifact.inspection_status === 'VERIFIED' ? '已验证' : '待核验' }}</small></div><em>›</em>
          </button>
        </details>
        <details class="context-section" :open="sources.length > 0">
          <summary>来源 <em>{{ sources.length }}</em></summary>
          <a v-for="source in sources" :key="source.id" class="source-row" :href="source.url" target="_blank" rel="noopener noreferrer">
            <span>↗</span><div><strong>{{ source.title || source.domain }}</strong><small>{{ source.domain }} · {{ source.source_agent || source.source_type }}</small></div>
          </a>
        </details>
        <details class="context-section" open>
          <summary>用量</summary>
          <div class="usage-grid">
            <span><small>调用</small><strong>{{ formatNumber(usage?.calls || 0) }}</strong></span>
            <span><small>输入</small><strong>{{ formatNumber(usage?.prompt_tokens || 0) }}</strong></span>
            <span><small>输出</small><strong>{{ formatNumber(usage?.completion_tokens || 0) }}</strong></span>
            <span><small>缓存</small><strong>{{ formatNumber(usage?.cache_hit_tokens || 0) }}</strong></span>
          </div>
        </details>
        <details class="context-section">
          <summary>工具记录 <em>{{ toolCalls.length }}</em></summary>
          <div v-for="call in toolCalls" :key="call.id" class="tool-summary"><strong>{{ call.tool_name }}</strong><small>{{ call.status }} · {{ call.result_summary || '等待结果' }}</small></div>
        </details>
        <div class="context-task-actions">
          <button v-if="running" type="button" @click="requestCancel">取消任务</button>
          <button v-if="task && ['FAILED', 'CANCELED'].includes(task.status)" type="button" @click="retryCurrent">重新执行</button>
          <button type="button" @click="archiveCurrent">归档</button>
        </div>
      </template>
    </aside>
  </section>
</template>
