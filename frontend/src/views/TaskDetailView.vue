<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant'
import { archiveTask, cancelTask, decideApproval, getEvents, getTask, getUsage, listApprovals, listArtifacts, listTaskMessages, listTaskNodes, listToolCalls, retryTask, sendTaskMessage } from '../api'
import type { Approval, Artifact, Task, TaskEvent, TaskMessage, TaskNode, ToolCall, UsageSummary } from '../types'

const route = useRoute()
const router = useRouter()
const taskId = String(route.params.id)
const task = ref<Task | null>(null)
const events = ref<TaskEvent[]>([])
const messages = ref<TaskMessage[]>([])
const artifacts = ref<Artifact[]>([])
const approvals = ref<Approval[]>([])
const nodes = ref<TaskNode[]>([])
const toolCalls = ref<ToolCall[]>([])
const usage = ref<UsageSummary | null>(null)
const loading = ref(true)
const chatInput = ref('')
const sendingMessage = ref(false)
let source: EventSource | null = null

const terminal = computed(() => task.value && ['SUCCEEDED', 'FAILED', 'CANCELED'].includes(task.value.status))
const canCancel = computed(() => task.value && !terminal.value && task.value.status !== 'CANCELING')
const canRetry = computed(() => task.value && ['FAILED', 'CANCELED'].includes(task.value.status))
const canRevise = computed(() => Boolean(terminal.value))

const nodeStatusLabels: Record<string, string> = {
  PENDING: '等待中', RUNNING: '执行中', SUCCEEDED: '已完成', FAILED: '失败', SKIPPED: '已跳过', CANCELED: '已取消',
}
const toolStatusLabels: Record<string, string> = {
  PENDING: '等待中', RUNNING: '执行中', SUCCEEDED: '成功', FAILED: '失败',
}
const approvalStatusLabels: Record<string, string> = {
  PENDING: '等待审批', APPROVED_ONCE: '已允许一次', APPROVED_FOR_TASK: '本任务已允许', DENIED: '已拒绝', EXPIRED: '已过期',
}

// —— 对话面板：上下文分组、自动滚动、回复指示 ——
const chatMessagesEl = ref<HTMLElement | null>(null)
const awaitingReply = ref(false)
let replyTimer: ReturnType<typeof setTimeout> | null = null

type ChatItem =
  | { kind: 'divider'; key: string; revision: number }
  | { kind: 'message'; key: string; message: TaskMessage }

// 按修订轮次插入分隔线，直观呈现多轮对话上下文
const chatItems = computed<ChatItem[]>(() => {
  const items: ChatItem[] = []
  let prevRevision: number | null = null
  for (const message of messages.value) {
    if (message.revision !== prevRevision) {
      items.push({ kind: 'divider', key: `divider-${message.revision}-${message.id}`, revision: message.revision })
      prevRevision = message.revision
    }
    items.push({ kind: 'message', key: message.id, message })
  }
  return items
})

function modeTag(mode: TaskMessage['mode']) {
  if (mode === 'revise') return '文件修改'
  if (mode === 'revision') return '修订结果'
  return ''
}

function scrollChatToBottom() {
  nextTick(() => {
    const el = chatMessagesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function stopAwaitingReply() {
  awaitingReply.value = false
  if (replyTimer) {
    clearTimeout(replyTimer)
    replyTimer = null
  }
}

// 用户上翻查看历史时不强制滚动；贴底或自己发言时才跟随到底部
const stickToBottom = ref(true)

function handleChatScroll() {
  const el = chatMessagesEl.value
  if (el) stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

watch(() => messages.value.length, () => {
  if (stickToBottom.value) scrollChatToBottom()
  if (messages.value.at(-1)?.role === 'assistant') stopAwaitingReply()
})

// Enter 发送、Shift+Enter 换行；中文输入法组词期间（isComposing）不触发
function handleChatKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    if (!sendingMessage.value) sendMessage('chat')
  }
}

async function load() {
  try {
    const [taskValue, eventValues, messageValues, artifactValues, approvalValues, nodeValues, callValues, usageValue] = await Promise.all([
      getTask(taskId), getEvents(taskId), listTaskMessages(taskId), listArtifacts(taskId),
      listApprovals(taskId), listTaskNodes(taskId), listToolCalls(taskId), getUsage(taskId),
    ])
    task.value = taskValue
    events.value = eventValues
    messages.value = messageValues
    artifacts.value = artifactValues
    approvals.value = approvalValues
    nodes.value = nodeValues
    toolCalls.value = callValues
    usage.value = usageValue
    // 已结束的任务不会再产生新事件，不建立 SSE，避免对已关闭的流无限重连
    if (!terminal.value) connectStream()
  } catch {
    showFailToast('任务加载失败')
  } finally {
    loading.value = false
  }
}

// —— SSE 数据刷新合并：高频事件（如 agent.progress）在短窗口内批量刷新，避免请求风暴 ——
type RefetchKey = 'nodes' | 'tools' | 'usage' | 'approvals' | 'artifacts' | 'messages'
const pendingRefetch = new Set<RefetchKey>()
let flushScheduled = false
let disposed = false

function scheduleRefetch(key: RefetchKey) {
  pendingRefetch.add(key)
  if (flushScheduled) return
  flushScheduled = true
  setTimeout(flushRefetch, 400)
}

async function flushRefetch() {
  flushScheduled = false
  if (disposed) return
  const keys = [...pendingRefetch]
  pendingRefetch.clear()
  try {
    task.value = await getTask(taskId)
    await Promise.all(keys.map(async (key) => {
      if (key === 'nodes') nodes.value = await listTaskNodes(taskId)
      else if (key === 'tools') toolCalls.value = await listToolCalls(taskId)
      else if (key === 'usage') usage.value = await getUsage(taskId)
      else if (key === 'approvals') approvals.value = await listApprovals(taskId)
      else if (key === 'artifacts') artifacts.value = await listArtifacts(taskId)
      else messages.value = await listTaskMessages(taskId)
    }))
  } catch {
    // 刷新失败静默忽略，后续事件会再次触发
  }
}

function connectStream() {
  source?.close()
  const lastId = events.value.at(-1)?.id ?? 0
  source = new EventSource(`/api/tasks/${taskId}/stream?last_event_id=${lastId}`, { withCredentials: true })
  const eventNames = [
    'task.created', 'task.queued', 'task.planning', 'plan.created', 'agent.started',
    'agent.progress', 'task.reviewing', 'task.packaging', 'task.completed', 'task.failed',
    'task.canceling', 'task.canceled', 'approval.required', 'approval.approved', 'approval.denied',
    'approval.auto_approved',
    'file.uploaded', 'artifact.created', 'artifact.updated', 'message.user', 'message.assistant',
    'task.revision.queued', 'tool.started', 'tool.completed', 'tool.failed',
  ]
  for (const name of eventNames) {
    source.addEventListener(name, (message) => {
      const raw = JSON.parse((message as MessageEvent).data)
      if (!events.value.some((item) => item.id === raw.id)) {
        events.value.push({ ...raw, event_type: raw.type })
      }
      if (raw.type.startsWith('agent.') || raw.type === 'plan.created') scheduleRefetch('nodes')
      if (raw.type.startsWith('tool.')) scheduleRefetch('tools')
      if (raw.type.startsWith('agent.') || raw.type.startsWith('task.')) scheduleRefetch('usage')
      if (raw.type.startsWith('approval.')) scheduleRefetch('approvals')
      if (raw.type === 'artifact.created' || raw.type === 'artifact.updated' || raw.type === 'file.uploaded') scheduleRefetch('artifacts')
      if (raw.type.startsWith('message.')) scheduleRefetch('messages')
      // 任务到达终态后主动关闭连接，避免浏览器对空流无限重连
      if (raw.type === 'task.completed' || raw.type === 'task.failed' || raw.type === 'task.canceled') source?.close()
    })
  }
}

async function sendMessage(mode: 'chat' | 'revise') {
  const content = chatInput.value.trim()
  if (!content) {
    showFailToast('请输入消息')
    return
  }
  sendingMessage.value = true
  try {
    await sendTaskMessage(taskId, content, mode)
    chatInput.value = ''
    stickToBottom.value = true // 自己发言后强制回到底部
    messages.value = await listTaskMessages(taskId)
    task.value = await getTask(taskId)
    connectStream()
    showSuccessToast(mode === 'revise' ? '文件修改已进入队列' : '消息已发送')
    if (mode === 'chat') {
      // 等待 Agent 回复期间显示输入指示，2 分钟无回复自动收起
      stopAwaitingReply()
      awaitingReply.value = true
      replyTimer = setTimeout(stopAwaitingReply, 120_000)
    }
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '消息发送失败')
  } finally {
    sendingMessage.value = false
  }
}

async function approve(approval: Approval, decision: 'deny' | 'allow_once' | 'allow_for_task') {
  try {
    await decideApproval(taskId, approval.id, decision)
    approvals.value = await listApprovals(taskId)
    showSuccessToast(decision === 'deny' ? '已拒绝' : '已批准')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '审批失败')
  }
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function requestCancel() {
  try {
    task.value = await cancelTask(taskId)
    showSuccessToast('已请求取消')
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '取消失败')
  }
}

async function retry() {
  try {
    task.value = await retryTask(taskId)
    showSuccessToast('已重新排队')
    connectStream()
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '重试失败')
  }
}

async function archive() {
  try {
    await showConfirmDialog({
      title: '归档任务？',
      message: '任务将从列表隐藏；服务器文件暂时保留，不会物理删除。',
      confirmButtonText: '确认归档',
    })
    await archiveTask(taskId)
    await router.replace('/')
  } catch (error: any) {
    if (error?.response) showFailToast(error.response.data?.detail || '归档失败')
  }
}

onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  source?.close()
  stopAwaitingReply()
})
</script>

<template>
  <section v-if="loading" class="empty-state">正在加载…</section>
  <section v-else-if="task" class="detail-page">
    <RouterLink to="/" class="back-link">← 返回任务</RouterLink>
    <div class="detail-header">
      <div>
        <p class="eyebrow">
          {{ task.task_type }} · {{ task.model_mode === 'auto' ? '自动模型' : task.model_mode }} ·
          {{ ({ auto: '智能', direct: '直接', normal: '常规', critical: '批判', bfs: '广度优先', dfs: '深度优先' } as Record<string, string>)[task.reasoning_mode] || task.reasoning_mode }}推理 ·
          {{ ({ smart: '智能', fast: '极速', medium: '中', high: '高', ultra: '极高' } as Record<string, string>)[task.reasoning_effort] || task.reasoning_effort }}强度 ·
          {{ task.autonomy_mode === 'yolo' ? 'YOLO 自主执行' : '安全审批' }}
        </p>
        <h1>{{ task.title }}</h1>
      </div>
      <strong>{{ task.progress }}%</strong>
    </div>
    <div class="progress-track large"><i :style="{ width: `${task.progress}%` }" /></div>
    <p class="current-step">{{ task.current_step || '等待执行' }}</p>

    <div class="action-row">
      <button v-if="canCancel" class="secondary-button danger" type="button" @click="requestCancel">取消任务</button>
      <button v-if="canRetry" class="secondary-button" type="button" @click="retry">重新执行</button>
      <button class="secondary-button danger" type="button" @click="archive">归档任务</button>
    </div>

    <article class="prompt-card">
      <h2>任务要求</h2>
      <p>{{ task.prompt }}</p>
    </article>

    <div class="section-heading">
      <h2>任务对话</h2>
      <small>上下文已保存 · 当前第 {{ task.current_revision }} 次修订</small>
    </div>
    <section class="chat-panel">
      <div ref="chatMessagesEl" class="chat-messages" @scroll="handleChatScroll">
        <div v-if="!messages.length" class="chat-empty">
          还没有对话。直接用自然语言描述想调整的地方，AI 会结合任务上下文回复；
          任务结束后点击“执行文件修改”，即可按整段对话生成新的文件版本。
        </div>
        <template v-for="item in chatItems" :key="item.key">
          <div v-if="item.kind === 'divider'" class="chat-divider"><span>第 {{ item.revision }} 次修订</span></div>
          <article
            v-if="item.kind === 'message'"
            :class="['chat-message', `chat-${item.message.role}`]"
          >
            <div>
              <strong>{{ item.message.role === 'user' ? '你' : 'Agent' }}</strong>
              <small>
                <span v-if="modeTag(item.message.mode)" class="chat-mode-tag">{{ modeTag(item.message.mode) }}</span>
                {{ new Date(item.message.created_at).toLocaleString() }}
              </small>
            </div>
            <p>{{ item.message.content }}</p>
          </article>
        </template>
        <article v-if="awaitingReply" class="chat-message chat-assistant">
          <span class="typing-dots"><i /><i /><i /></span>
        </article>
      </div>
      <textarea
        v-model="chatInput"
        rows="4"
        maxlength="20000"
        :disabled="sendingMessage"
        placeholder="继续询问，或描述要对现有文件做的修改…（Enter 发送，Shift+Enter 换行）"
        @keydown="handleChatKeydown"
      />
      <div class="chat-actions">
        <button class="secondary-button" type="button" :disabled="sendingMessage" @click="sendMessage('chat')">
          {{ sendingMessage ? '发送中…' : '发送消息' }}
        </button>
        <button class="primary-button" type="button" :disabled="sendingMessage || !canRevise" @click="sendMessage('revise')">
          执行文件修改
        </button>
      </div>
      <small class="muted chat-hint">
        {{ canRevise
          ? '对话会作为上下文持续保存，点击“执行文件修改”将按整段对话生成新修订。'
          : '对话会作为上下文持续保存；任务结束后可点击“执行文件修改”按对话生成新修订。' }}
      </small>
    </section>

    <template v-if="nodes.length">
      <div class="section-heading"><h2>Agent 执行计划</h2></div>
      <div class="agent-grid">
        <article v-for="node in nodes" :key="node.id" class="agent-card">
          <div class="agent-card-top">
            <span>{{ node.role }}</span>
            <strong>{{ nodeStatusLabels[node.status] || node.status }}</strong>
          </div>
          <h3>{{ node.title }}</h3>
          <p>{{ node.instructions }}</p>
          <small>依赖：{{ node.depends_on.length ? node.depends_on.join(', ') : '无' }} · 尝试 {{ node.attempt }}</small>
        </article>
      </div>
    </template>

    <template v-if="approvals.length">
      <div class="section-heading"><h2>操作审批</h2></div>
      <article v-for="approval in approvals" :key="approval.id" class="approval-card">
        <div>
          <span class="risk-label">{{ approval.risk }} risk</span>
          <strong>{{ approval.operation }}</strong>
          <p>{{ approval.summary }}</p>
        </div>
        <div v-if="approval.status === 'PENDING'" class="approval-actions">
          <button class="secondary-button danger" type="button" @click="approve(approval, 'deny')">拒绝</button>
          <button class="secondary-button" type="button" @click="approve(approval, 'allow_once')">允许一次</button>
          <button class="secondary-button" type="button" @click="approve(approval, 'allow_for_task')">本任务允许</button>
        </div>
        <small v-else>{{ approvalStatusLabels[approval.status] || approval.status }}</small>
      </article>
    </template>

    <template v-if="artifacts.length">
      <div class="section-heading"><h2>任务文件</h2></div>
      <div class="artifact-list">
        <a
          v-for="artifact in artifacts"
          :key="artifact.id"
          class="artifact-card"
          :href="`/api/tasks/${taskId}/artifacts/${artifact.id}/download`"
        >
          <div><strong>{{ artifact.filename }}</strong><small>{{ artifact.relative_path }}</small></div>
          <span>{{ formatSize(artifact.size) }} ↓</span>
        </a>
      </div>
    </template>

    <template v-if="toolCalls.length">
      <div class="section-heading"><h2>工具调用</h2></div>
      <div class="tool-list">
        <div v-for="call in toolCalls" :key="call.id" class="tool-row">
          <strong>{{ call.tool_name }}</strong>
          <span>{{ toolStatusLabels[call.status] || call.status }}</span>
          <small>{{ call.result_summary || '等待结果' }}</small>
        </div>
      </div>
    </template>

    <div v-if="usage" class="usage-card">
      <span>模型调用 <strong>{{ usage.calls }}</strong></span>
      <span>输入 Token <strong>{{ usage.prompt_tokens }}</strong></span>
      <span>输出 Token <strong>{{ usage.completion_tokens }}</strong></span>
      <span>缓存命中 <strong>{{ usage.cache_hit_tokens }}</strong></span>
    </div>

    <div class="section-heading"><h2>实时进度</h2></div>
    <ol class="timeline">
      <li v-for="event in events" :key="event.id">
        <span class="timeline-dot" />
        <div>
          <strong>{{ event.title }}</strong>
          <p v-if="event.content">{{ event.content }}</p>
          <small>{{ new Date(event.created_at).toLocaleTimeString() }}</small>
        </div>
      </li>
    </ol>
  </section>
</template>
