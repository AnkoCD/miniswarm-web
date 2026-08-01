<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast } from 'vant'
import { apiErrorMessage, createTask, deleteTask, listSkills, listTasks, startTask, uploadTaskFile } from '../api'
import type { Skill, Task } from '../types'

const tasks = ref<Task[]>([])
const prompt = ref('')
const taskType = ref('auto')
const modelMode = ref('auto')
const reasoningMode = ref<'auto' | 'direct' | 'normal' | 'critical' | 'bfs' | 'dfs'>('auto')
const reasoningEffort = ref<'smart' | 'fast' | 'medium' | 'high' | 'ultra'>('smart')
const executionMode = computed(() =>
  ['medium', 'high', 'ultra'].includes(reasoningEffort.value) ? 'deep' : 'standard',
)
const autonomyMode = ref('safe')
const skillMode = ref<'auto' | 'manual' | 'off'>('auto')
const selectedSkills = ref<string[]>([])
const skills = ref<Skill[]>([])
const loading = ref(true)
const submitting = ref(false)
const selectedFiles = ref<File[]>([])
const router = useRouter()

const statusLabels: Record<string, string> = {
  CREATED: '已创建', QUEUED: '排队中', PLANNING: '规划中', RUNNING: '执行中',
  WAITING_APPROVAL: '等待审批', REVIEWING: '检查中', REWORKING: '返工中',
  PACKAGING: '打包中', SUCCEEDED: '已完成', FAILED: '失败', CANCELING: '取消中', CANCELED: '已取消',
}

async function refresh() {
  loading.value = true
  try {
    ;[tasks.value, skills.value] = await Promise.all([listTasks(), listSkills()])
  } catch {
    showFailToast('任务列表加载失败')
  } finally {
    loading.value = false
  }
}

async function submit() {
  const value = prompt.value.trim()
  if (!value) {
    showFailToast('请输入任务内容')
    return
  }
  if (skillMode.value === 'manual' && selectedSkills.value.length === 0) {
    showFailToast('手动模式至少选择一个 Skill')
    return
  }
  submitting.value = true
  try {
    const task = await createTask({
      prompt: value,
      task_type: taskType.value,
      model_mode: modelMode.value,
      execution_mode: executionMode.value,
      reasoning_mode: reasoningMode.value,
      reasoning_effort: reasoningEffort.value,
      autonomy_mode: autonomyMode.value,
      skill_mode: skillMode.value,
      selected_skills: selectedSkills.value,
      start_immediately: selectedFiles.value.length === 0,
    })
    if (selectedFiles.value.length) {
      try {
        for (const file of selectedFiles.value) await uploadTaskFile(task.id, file)
        await startTask(task.id)
      } catch (uploadError) {
        // 上传或启动失败：归档未启动的草稿任务，避免留下无法操作的残留
        await deleteTask(task.id).catch(() => undefined)
        throw uploadError
      }
    }
    prompt.value = ''
    selectedFiles.value = []
    await router.push(`/tasks/${task.id}`)
  } catch (error: any) {
    showFailToast(apiErrorMessage(error, '任务创建失败'))
  } finally {
    submitting.value = false
  }
}

const MAX_FILE_SIZE = 100 * 1024 * 1024 // 与界面说明一致：单文件最大 100 MB

function chooseFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  const oversized = files.filter((file) => file.size > MAX_FILE_SIZE)
  if (oversized.length) {
    showFailToast(`超过 100 MB：${oversized.map((file) => file.name).join('、')}`)
    input.value = ''
    selectedFiles.value = []
    return
  }
  selectedFiles.value = files
}

onMounted(refresh)
</script>

<template>
  <section>
    <div class="hero-copy">
      <p class="eyebrow">云端执行台</p>
      <h1>今天交给 Agent 做什么？</h1>
      <p class="muted">每位用户同时运行一个主任务，复杂任务由系统决定是否并行。</p>
    </div>

    <form class="composer" @submit.prevent="submit">
      <textarea v-model="prompt" rows="5" maxlength="20000" placeholder="例如：分析上传的数据并生成一份 PDF 报告" />
      <div class="composer-options">
        <label>
          <span>任务类型</span>
          <select v-model="taskType">
            <option value="auto">自动识别</option>
            <option value="document">文档制作</option>
            <option value="code">代码任务</option>
            <option value="data">数据处理</option>
            <option value="file">文件处理</option>
          </select>
        </label>
        <label>
          <span>模型</span>
          <select v-model="modelMode">
            <option value="auto">自动：Pro 规划/审查，Flash 执行</option>
            <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
            <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
          </select>
        </label>
        <label>
          <span>推理模式</span>
          <select v-model="reasoningMode">
            <option value="auto">智能选择</option>
            <option value="direct">直接回答</option>
            <option value="normal">常规推理</option>
            <option value="critical">批判推理</option>
            <option value="bfs">广度优先</option>
            <option value="dfs">深度优先</option>
          </select>
        </label>
        <label>
          <span>推理强度</span>
          <select v-model="reasoningEffort">
            <option value="smart">智能</option>
            <option value="fast">极速</option>
            <option value="medium">中</option>
            <option value="high">高</option>
            <option value="ultra">极高</option>
          </select>
        </label>
        <label>
          <span>自主执行</span>
          <select v-model="autonomyMode">
            <option value="safe">安全模式（风险操作需确认）</option>
            <option value="yolo">YOLO 模式（自动执行可恢复操作）</option>
          </select>
        </label>
      </div>
      <p v-if="autonomyMode === 'yolo'" class="muted">
        YOLO 会自动批准任务目录内的覆盖、移动和公开网络检索；删除、越界路径、宿主机操作及文件外传仍会拦截。
      </p>
      <div class="skill-chooser">
        <label>
          <span>Skill 使用方式</span>
          <select v-model="skillMode">
            <option value="auto">自主判断（推荐）</option>
            <option value="manual">仅使用我选择的 Skill</option>
            <option value="off">本任务不使用 Skill</option>
          </select>
        </label>
        <p v-if="skillMode === 'auto'" class="muted">
          系统会按任务内容和 Agent 角色自动选择；勾选项会优先启用。
        </p>
        <div v-if="skillMode !== 'off'" class="skill-grid">
          <label
            v-for="skill in skills"
            :key="skill.name"
            :class="['skill-card', { selected: selectedSkills.includes(skill.name) }]"
          >
            <input v-model="selectedSkills" type="checkbox" :value="skill.name" />
            <span>
              <strong>{{ skill.display_name }}</strong>
              <small>{{ skill.description }}</small>
            </span>
          </label>
        </div>
      </div>
      <label class="file-picker">
        <span>任务文件（可多选，单文件最大 100 MB）</span>
        <input type="file" multiple @change="chooseFiles" />
      </label>
      <div v-if="selectedFiles.length" class="selected-files">
        <span v-for="file in selectedFiles" :key="`${file.name}-${file.size}`">{{ file.name }}</span>
      </div>
      <button class="primary-button" type="submit" :disabled="submitting">
        {{ submitting ? '正在创建…' : '开始任务' }}
      </button>
    </form>

    <div class="section-heading">
      <h2>最近任务</h2>
      <button type="button" class="text-button" @click="refresh">刷新</button>
    </div>
    <div v-if="loading" class="empty-state">正在加载…</div>
    <div v-else-if="!tasks.length" class="empty-state">还没有任务</div>
    <div v-else class="task-list">
      <RouterLink v-for="task in tasks" :key="task.id" :to="`/tasks/${task.id}`" class="task-card">
        <div class="task-card-top">
          <strong>{{ task.title }}</strong>
          <span :class="['status-chip', `status-${task.status.toLowerCase()}`]">{{ statusLabels[task.status] }}</span>
        </div>
        <p>{{ task.current_step || '等待处理' }}</p>
        <div class="progress-track"><i :style="{ width: `${task.progress}%` }" /></div>
        <small>{{ new Date(task.created_at).toLocaleString() }} · {{ task.progress }}%</small>
      </RouterLink>
    </div>
  </section>
</template>
