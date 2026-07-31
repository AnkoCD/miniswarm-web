import axios from 'axios'
import type { Approval, ArchivedTask, Artifact, ArtifactPreview, MemoryExtraction, Project, ProjectFile, ProjectMember, ProjectMemoryBundle, ProjectRole, SearchItem, Skill, SkillInstallResult, SkillRemoveResult, SystemConfig, Task, TaskEvent, TaskMessage, TaskNode, TaskSource, TaskSupervision, ToolCall, UsageSummary, User, UserMemory, UserMemoryProfile, UserRole, WorkerStatus } from './types'

export const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  timeout: 20_000,
})

export function redirectToLogin() {
  if (window.location.pathname === '/login') return
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  sessionStorage.setItem('miniswarm:session-expired', 'true')
  window.location.replace(`/login?expired=1&next=${next}`)
}

export function apiErrorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .slice(0, 3)
      .map((item: any) => {
        const field = Array.isArray(item?.loc)
          ? item.loc.filter((part: unknown) => part !== 'body').join('.')
          : ''
        const fieldLabels: Record<string, string> = {
          prompt: '输入内容',
          project_id: '项目',
          project_file_ids: '项目文件',
          task_type: '任务类型',
          model_mode: '模型',
          execution_mode: '思考模式',
          autonomy_mode: '安全模式',
          skill_mode: 'Skill 模式',
          selected_skills: 'Skills',
          client_request_id: '请求编号',
        }
        const label = fieldLabels[field] || field || '请求参数'
        if (item?.type === 'string_too_short') return `${label}过短`
        if (item?.type === 'string_too_long') return `${label}过长`
        if (item?.type === 'literal_error' || item?.type === 'string_pattern_mismatch') {
          return `${label}选项无效，请刷新页面后重试`
        }
        return `${label}：${item?.msg || '格式不正确'}`
      })
      .join('；')
  }
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message
  }
  if (!error?.response) return '无法连接服务器，请检查网络后重试'
  return fallback
}

// 会话过期（401）时统一跳转登录页，并带上回跳地址
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && window.location.pathname !== '/login') {
      redirectToLogin()
    }
    return Promise.reject(error)
  },
)

export async function login(username: string, password: string): Promise<User> {
  const { data } = await api.post<User>('/auth/login', { username, password })
  return data
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout')
}

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>('/auth/me')
  return data
}

export async function listTasks(): Promise<Task[]> {
  const { data } = await api.get<{ items: Task[] }>('/tasks')
  return data.items
}

export async function listSkills(): Promise<Skill[]> {
  const { data } = await api.get<Skill[]>('/skills')
  return data
}

export async function installSkill(url: string): Promise<SkillInstallResult> {
  const { data } = await api.post<SkillInstallResult>(
    '/skills/install',
    { url },
    { timeout: 330_000 },
  )
  return data
}

export async function removeSkill(name: string): Promise<SkillRemoveResult> {
  const { data } = await api.delete<SkillRemoveResult>(`/skills/${encodeURIComponent(name)}`)
  return data
}

export async function createTask(payload: {
  prompt: string
  title?: string
  task_type: string
  model_mode: string
  execution_mode: string
  autonomy_mode: string
  skill_mode: 'auto' | 'manual' | 'off'
  selected_skills: string[]
  start_immediately?: boolean
  project_id?: string
  project_file_ids?: string[]
  execution_kind?: 'auto' | 'chat' | 'task' | 'revision'
  client_request_id?: string
  web_search?: boolean
}): Promise<Task> {
  const { data } = await api.post<Task>('/tasks', payload)
  return data
}

export async function uploadTaskFile(taskId: string, file: File): Promise<Artifact> {
  const form = new FormData()
  form.append('upload', file)
  const { data } = await api.post<Artifact>(`/tasks/${taskId}/files`, form)
  return data
}

export async function startTask(id: string): Promise<Task> {
  const { data } = await api.post<Task>(`/tasks/${id}/start`)
  return data
}

export async function startChat(id: string, webSearch = false): Promise<Task> {
  const { data } = await api.post<Task>(`/tasks/${id}/chat-start`, undefined, {
    params: { web_search: webSearch },
  })
  return data
}

export async function getTask(id: string): Promise<Task> {
  const { data } = await api.get<Task>(`/tasks/${id}`)
  return data
}

export async function listTaskMessages(id: string): Promise<TaskMessage[]> {
  const { data } = await api.get<TaskMessage[]>(`/tasks/${id}/messages`)
  return data
}

export async function getTaskSupervision(id: string): Promise<TaskSupervision> {
  const { data } = await api.get<TaskSupervision>(`/tasks/${id}/supervision`)
  return data
}

export async function sendTaskMessage(
  id: string,
  content: string,
  mode: 'auto' | 'chat' | 'revise' | 'task',
  clientMessageId?: string,
  options?: { executionMode?: 'standard' | 'deep'; webSearch?: boolean },
): Promise<TaskMessage> {
  const { data } = await api.post<TaskMessage>(`/tasks/${id}/messages`, {
    content,
    mode,
    client_message_id: clientMessageId,
    execution_mode: options?.executionMode,
    web_search: options?.webSearch || false,
  })
  return data
}

export async function getEvents(id: string, afterId = 0): Promise<TaskEvent[]> {
  const { data } = await api.get<{ items: TaskEvent[] }>(`/tasks/${id}/events`, {
    params: { after_id: afterId },
  })
  return data.items
}

export async function cancelTask(id: string): Promise<Task> {
  const { data } = await api.post<Task>(`/tasks/${id}/cancel`)
  return data
}

export async function retryTask(id: string): Promise<Task> {
  const { data } = await api.post<Task>(`/tasks/${id}/retry`)
  return data
}

export async function deleteTask(id: string): Promise<void> {
  await api.delete(`/tasks/${id}`)
}

export async function archiveTask(id: string): Promise<{ task: Task; memory_status: string }> {
  const { data } = await api.post(`/tasks/${id}/archive`)
  return data
}

export async function listArchivedTasks(params: Record<string, unknown> = {}): Promise<{ items: ArchivedTask[]; total: number }> {
  const { data } = await api.get<{ items: ArchivedTask[]; total: number }>('/tasks/archived', { params })
  return data
}

export async function restoreTask(id: string): Promise<Task> {
  const { data } = await api.post<Task>(`/tasks/${id}/restore`)
  return data
}

export async function retryArchiveAnalysis(id: string): Promise<MemoryExtraction> {
  const { data } = await api.post<MemoryExtraction>(`/tasks/${id}/archive-analysis/retry`)
  return data
}

export async function listMemories(params: Record<string, unknown> = {}): Promise<{ items: UserMemory[]; total: number }> {
  const { data } = await api.get<{ items: UserMemory[]; total: number }>('/memories', { params })
  return data
}

export async function getMemoryProfile(): Promise<UserMemoryProfile> {
  const { data } = await api.get<UserMemoryProfile>('/memories/profile')
  return data
}

export async function updateMemory(id: string, payload: { statement?: string; category?: string; confidence?: number }): Promise<UserMemory> {
  const { data } = await api.patch<UserMemory>(`/memories/${id}`, payload)
  return data
}

export async function activateMemory(id: string): Promise<UserMemory> {
  const { data } = await api.post<UserMemory>(`/memories/${id}/activate`)
  return data
}

export async function disableMemory(id: string): Promise<UserMemory> {
  const { data } = await api.post<UserMemory>(`/memories/${id}/disable`)
  return data
}

export async function listArtifacts(id: string): Promise<Artifact[]> {
  const { data } = await api.get<Artifact[]>(`/tasks/${id}/artifacts`)
  return data
}

export async function listApprovals(id: string): Promise<Approval[]> {
  const { data } = await api.get<Approval[]>(`/tasks/${id}/approvals`)
  return data
}

export async function decideApproval(
  taskId: string,
  approvalId: string,
  decision: 'deny' | 'allow_once' | 'allow_for_task',
): Promise<Approval> {
  const { data } = await api.post<Approval>(`/tasks/${taskId}/approvals/${approvalId}`, { decision })
  return data
}

export async function listTaskNodes(id: string): Promise<TaskNode[]> {
  const { data } = await api.get<TaskNode[]>(`/tasks/${id}/nodes`)
  return data
}

export async function listToolCalls(id: string): Promise<ToolCall[]> {
  const { data } = await api.get<ToolCall[]>(`/tasks/${id}/tool-calls`)
  return data
}

export async function getUsage(id: string): Promise<UsageSummary> {
  const { data } = await api.get<UsageSummary>(`/tasks/${id}/usage`)
  return data
}

export async function listUsers(): Promise<User[]> {
  const { data } = await api.get<User[]>('/admin/users')
  return data
}

export async function createUser(payload: { username: string; password: string; role: UserRole }): Promise<User> {
  const { data } = await api.post<User>('/admin/users', payload)
  return data
}

export async function getSystemConfig(): Promise<SystemConfig> {
  const { data } = await api.get<SystemConfig>('/admin/system')
  return data
}

export async function getWorkers(): Promise<WorkerStatus[]> {
  const { data } = await api.get<WorkerStatus[]>('/admin/workers')
  return data
}

export async function listProjects(includeArchived = false): Promise<Project[]> {
  const { data } = await api.get<{ items: Project[] }>('/projects', {
    params: { include_archived: includeArchived },
  })
  return data.items
}

export async function createProject(payload: { name: string; description?: string }): Promise<Project> {
  const { data } = await api.post<Project>('/projects', payload)
  return data
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/projects/${id}`)
  return data
}

export async function updateProject(id: string, payload: Partial<Pick<Project, 'name' | 'description' | 'is_pinned'>>): Promise<Project> {
  const { data } = await api.patch<Project>(`/projects/${id}`, payload)
  return data
}

export async function archiveProject(id: string): Promise<Project> {
  const { data } = await api.post<Project>(`/projects/${id}/archive`)
  return data
}

export async function restoreProject(id: string): Promise<Project> {
  const { data } = await api.post<Project>(`/projects/${id}/restore`)
  return data
}

export async function listProjectMembers(id: string): Promise<ProjectMember[]> {
  const { data } = await api.get<ProjectMember[]>(`/projects/${id}/members`)
  return data
}

export async function addProjectMember(id: string, username: string, role: ProjectRole): Promise<ProjectMember> {
  const { data } = await api.post<ProjectMember>(`/projects/${id}/members`, { username, role })
  return data
}

export async function updateProjectMember(id: string, userId: string, role: ProjectRole): Promise<ProjectMember> {
  const { data } = await api.patch<ProjectMember>(`/projects/${id}/members/${userId}`, { role })
  return data
}

export async function removeProjectMember(id: string, userId: string): Promise<void> {
  await api.delete(`/projects/${id}/members/${userId}`)
}

export async function listProjectFiles(id: string): Promise<ProjectFile[]> {
  const { data } = await api.get<ProjectFile[]>(`/projects/${id}/files`)
  return data
}

export async function uploadProjectFile(id: string, file: File): Promise<ProjectFile> {
  const form = new FormData()
  form.append('upload', file)
  const { data } = await api.post<ProjectFile>(`/projects/${id}/files`, form)
  return data
}

export async function archiveProjectFile(id: string, fileId: string): Promise<ProjectFile> {
  const { data } = await api.post<ProjectFile>(`/projects/${id}/files/${fileId}/archive`)
  return data
}

export async function listProjectTasks(id: string): Promise<Task[]> {
  const { data } = await api.get<{ items: Task[] }>(`/projects/${id}/tasks`)
  return data.items
}

export async function getProjectMemories(id: string): Promise<ProjectMemoryBundle> {
  const { data } = await api.get<ProjectMemoryBundle>(`/projects/${id}/memories`)
  return data
}

export async function listTaskSources(id: string): Promise<TaskSource[]> {
  const { data } = await api.get<TaskSource[]>(`/tasks/${id}/sources`)
  return data
}

export async function getArtifactPreview(id: string, artifactId: string): Promise<ArtifactPreview> {
  const { data } = await api.get<ArtifactPreview>(`/tasks/${id}/artifacts/${artifactId}/preview-metadata`)
  return data
}

export async function searchWorkspace(q: string, offset = 0): Promise<{ items: SearchItem[]; total: number }> {
  const { data } = await api.get<{ items: SearchItem[]; total: number }>('/search', {
    params: { q, offset, limit: 50 },
  })
  return data
}
