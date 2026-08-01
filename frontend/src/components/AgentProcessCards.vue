<script setup lang="ts">
import { computed } from 'vue'
import type { Artifact, Task, TaskEvent, TaskNode, ToolCall } from '../types'

const props = defineProps<{
  task: Task
  nodes: TaskNode[]
  events: TaskEvent[]
  toolCalls: ToolCall[]
  artifacts: Artifact[]
}>()

const statusText: Record<string, string> = {
  PENDING: '等待依赖',
  READY: '准备执行',
  QUEUED: '排队中',
  RUNNING: '执行中',
  WAITING: '等待审批',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELED: '已取消',
}

const roleText: Record<string, string> = {
  researcher: '研究',
  reader: '阅读',
  data_analyst: '数据',
  coder: '代码',
  document: '文档',
  file_worker: '文件',
  reviewer: '审核',
}

const visibleEvents = computed(() => props.events
  .filter(event => !event.event_type.startsWith('message.'))
  .slice(-8)
  .reverse())

const activeNodes = computed(() => props.nodes.filter(node =>
  ['READY', 'QUEUED', 'RUNNING', 'WAITING'].includes(node.status),
))

const overallIntent = computed(() => {
  if (activeNodes.value.length) {
    return activeNodes.value.map(node => node.title).join('；')
  }
  if (props.task.current_step) return props.task.current_step
  if (props.task.status === 'SUCCEEDED') return '核对交付物并结束任务'
  return props.task.prompt
})

function progressFor(node: TaskNode) {
  if (node.status === 'SUCCEEDED') return 100
  if (node.status === 'FAILED' || node.status === 'CANCELED') return 100
  if (node.status === 'RUNNING') return 68
  if (node.status === 'QUEUED' || node.status === 'READY') return 28
  if (node.status === 'WAITING') return 55
  return 8
}

function toolsFor(node: TaskNode) {
  return props.toolCalls
    .filter(call => call.node_id === node.id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
}

function artifactsFor(node: TaskNode) {
  return props.artifacts.filter(artifact => artifact.node_id === node.id)
}

function isOpenByDefault(node: TaskNode) {
  return ['RUNNING', 'WAITING', 'FAILED'].includes(node.status)
}

function formatTime(value: string | null) {
  if (!value) return ''
  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function toolTitle(call: ToolCall) {
  const names: Record<string, string> = {
    anysearch: '检索资料',
    search_news: '搜索新闻',
    write_text: '写入工作文件',
    run_python: '运行生成脚本',
    inspect_document: '检查文档',
    convert_document: '转换文件',
    convert_to_markdown: '读取文档内容',
    list_files: '查看文件',
    read_text: '读取文本',
  }
  return names[call.tool_name] || call.tool_name
}
</script>

<template>
  <section class="process-cards" aria-label="任务执行过程">
    <details class="process-overview" open>
      <summary>
        <span class="process-icon">✦</span>
        <div>
          <strong>执行过程</strong>
          <small>{{ task.current_step || statusText[task.status] || task.status }}</small>
        </div>
        <em>{{ task.progress }}%</em>
      </summary>
      <div class="process-overview-body">
        <section>
          <h4>我要干什么</h4>
          <p>{{ overallIntent }}</p>
        </section>
        <section>
          <h4>我干了什么</h4>
          <ol v-if="visibleEvents.length" class="process-event-list">
            <li v-for="event in visibleEvents" :key="event.id">
              <i />
              <div>
                <strong>{{ event.title }}</strong>
                <small v-if="event.content">{{ event.content }}</small>
              </div>
              <time>{{ formatTime(event.created_at) }}</time>
            </li>
          </ol>
          <p v-else class="empty-process">正在准备执行记录…</p>
        </section>
      </div>
    </details>

    <div class="agent-card-heading">
      <strong>子 Agent</strong>
      <span>{{ nodes.length }} 个节点 · 点击卡片查看过程</span>
    </div>

    <details
      v-for="node in nodes"
      :key="node.id"
      class="agent-process-card"
      :open="isOpenByDefault(node)"
    >
      <summary>
        <span class="agent-role">{{ (roleText[node.role] || node.role).slice(0, 1) }}</span>
        <div class="agent-summary-copy">
          <strong>{{ node.title }}</strong>
          <small>{{ roleText[node.role] || node.role }} Agent · {{ statusText[node.status] || node.status }}</small>
          <i class="agent-progress"><b :style="{ width: `${progressFor(node)}%` }" /></i>
        </div>
        <span :class="['agent-status', `is-${node.status.toLowerCase()}`]">
          {{ statusText[node.status] || node.status }}
        </span>
      </summary>

      <div class="agent-process-body">
        <section class="agent-intent">
          <h4>我要干什么</h4>
          <p>{{ node.instructions }}</p>
          <small v-if="node.depends_on.length">依赖：{{ node.depends_on.join('、') }}</small>
        </section>

        <section class="agent-actions">
          <h4>我干了什么</h4>
          <ol>
            <li v-if="node.started_at">
              <i class="done" />
              <div><strong>开始执行</strong><small>{{ node.title }}</small></div>
              <time>{{ formatTime(node.started_at) }}</time>
            </li>
            <li v-for="call in toolsFor(node)" :key="call.id">
              <i :class="call.status === 'SUCCEEDED' ? 'done' : call.status === 'FAILED' ? 'failed' : 'running'" />
              <div>
                <strong>{{ toolTitle(call) }}</strong>
                <small>{{ call.result_summary || call.status }}</small>
              </div>
              <time>{{ formatTime(call.completed_at || call.created_at) }}</time>
            </li>
            <li v-for="artifact in artifactsFor(node)" :key="artifact.id">
              <i class="done" />
              <div>
                <strong>生成文件</strong>
                <small>{{ artifact.relative_path }}</small>
              </div>
              <time>{{ formatTime(artifact.created_at) }}</time>
            </li>
            <li v-if="node.result_summary">
              <i :class="node.status === 'FAILED' ? 'failed' : 'done'" />
              <div>
                <strong>{{ node.status === 'FAILED' ? '执行结果' : '完成总结' }}</strong>
                <small>{{ node.result_summary }}</small>
              </div>
              <time>{{ formatTime(node.completed_at) }}</time>
            </li>
            <li v-if="!node.started_at && !toolsFor(node).length && !node.result_summary" class="agent-empty-action">
              <i />
              <div><strong>等待执行</strong><small>依赖完成后会自动开始</small></div>
            </li>
          </ol>
        </section>
      </div>
    </details>
  </section>
</template>

<style scoped>
.process-cards {
  width: min(820px, 100%);
  margin: 0 auto 30px;
}
.process-overview,
.agent-process-card {
  overflow: hidden;
  border: 1px solid var(--ws-line);
  border-radius: 13px;
  background: var(--ws-bg);
}
.process-overview { margin-bottom: 14px; }
.process-overview > summary,
.agent-process-card > summary {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 14px;
  cursor: pointer;
  list-style: none;
}
.process-overview > summary::-webkit-details-marker,
.agent-process-card > summary::-webkit-details-marker { display: none; }
.process-overview > summary:hover,
.agent-process-card > summary:hover { background: var(--ws-soft); }
.process-icon,
.agent-role {
  display: grid;
  width: 30px;
  height: 30px;
  flex: none;
  place-items: center;
  border-radius: 9px;
  color: #fff;
  background: var(--ws-text);
  font-size: 12px;
  font-weight: 750;
}
.process-overview summary > div,
.agent-summary-copy { display: grid; min-width: 0; flex: 1; gap: 2px; }
.process-overview summary strong,
.agent-summary-copy strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.process-overview summary small,
.agent-summary-copy small { color: var(--ws-muted); font-size: 10px; }
.process-overview summary em { color: var(--ws-muted); font-size: 11px; font-style: normal; }
.process-overview-body {
  display: grid;
  grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr);
  gap: 0;
  border-top: 1px solid var(--ws-line);
}
.process-overview-body > section { padding: 14px; }
.process-overview-body > section + section { border-left: 1px solid var(--ws-line); }
.process-overview h4,
.agent-process-body h4 {
  margin: 0 0 8px;
  color: var(--ws-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .04em;
}
.process-overview p,
.agent-process-body p { margin: 0; font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.process-event-list,
.agent-actions ol { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.process-event-list li,
.agent-actions li {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: start;
  gap: 9px;
}
.process-event-list li > i,
.agent-actions li > i {
  width: 7px;
  height: 7px;
  margin-top: 4px;
  border: 1px solid var(--ws-line-strong);
  border-radius: 50%;
  background: var(--ws-bg);
}
.process-event-list li > i,
.agent-actions li > i.done { border-color: #3c936a; background: #3c936a; }
.agent-actions li > i.running { border-color: #3978f6; background: #3978f6; box-shadow: 0 0 0 3px rgba(57, 120, 246, .12); }
.agent-actions li > i.failed { border-color: #d14d41; background: #d14d41; }
.process-event-list li > div,
.agent-actions li > div { display: grid; min-width: 0; gap: 2px; }
.process-event-list strong,
.agent-actions strong { font-size: 11px; font-weight: 600; }
.process-event-list small,
.agent-actions small { overflow-wrap: anywhere; color: var(--ws-muted); font-size: 10px; line-height: 1.45; }
.process-event-list time,
.agent-actions time { color: var(--ws-muted); font-size: 9px; white-space: nowrap; }
.empty-process { color: var(--ws-muted); }
.agent-card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 18px 2px 8px;
}
.agent-card-heading strong { font-size: 12px; }
.agent-card-heading span { color: var(--ws-muted); font-size: 10px; }
.agent-process-card { margin-bottom: 8px; }
.agent-role { color: var(--ws-text); border: 1px solid var(--ws-line-strong); background: var(--ws-soft); }
.agent-progress {
  display: block;
  width: min(210px, 100%);
  height: 3px;
  margin-top: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ws-line);
}
.agent-progress b { display: block; height: 100%; border-radius: inherit; background: var(--ws-green); transition: width .25s ease; }
.agent-status {
  padding: 4px 7px;
  border-radius: 999px;
  color: var(--ws-muted);
  background: var(--ws-soft);
  font-size: 9px;
  white-space: nowrap;
}
.agent-status.is-running { color: #2368d8; background: #edf4ff; }
.agent-status.is-succeeded { color: #13734b; background: #eaf7f0; }
.agent-status.is-failed { color: #b33329; background: #fff0ee; }
.agent-status.is-waiting { color: #995b00; background: #fff1d7; }
.agent-process-body {
  display: grid;
  grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
  border-top: 1px solid var(--ws-line);
  background: var(--ws-soft);
}
.agent-process-body > section { padding: 14px; }
.agent-process-body > section + section { border-left: 1px solid var(--ws-line); }
.agent-intent > small { display: block; margin-top: 9px; color: var(--ws-muted); font-size: 9px; }
.agent-empty-action { color: var(--ws-muted); }
@media (max-width: 700px) {
  .process-overview-body,
  .agent-process-body { grid-template-columns: 1fr; }
  .process-overview-body > section + section,
  .agent-process-body > section + section { border-top: 1px solid var(--ws-line); border-left: 0; }
  .agent-card-heading span { display: none; }
}
</style>
