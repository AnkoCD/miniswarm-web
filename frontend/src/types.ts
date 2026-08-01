export type UserRole = 'admin' | 'user'

export interface User {
  id: string
  username: string
  role: UserRole
}

export type TaskStatus =
  | 'CREATED'
  | 'QUEUED'
  | 'PLANNING'
  | 'RUNNING'
  | 'WAITING_APPROVAL'
  | 'REVIEWING'
  | 'REWORKING'
  | 'PACKAGING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELING'
  | 'CANCELED'

export interface Task {
  id: string
  owner_id: string
  project_id: string | null
  created_by: string | null
  execution_kind: 'chat' | 'task' | 'revision'
  title: string
  prompt: string
  task_type: string
  execution_mode: string
  reasoning_mode: 'auto' | 'direct' | 'normal' | 'critical' | 'bfs' | 'dfs'
  reasoning_effort: 'smart' | 'fast' | 'medium' | 'high' | 'ultra'
  autonomy_mode: 'safe' | 'yolo'
  model_mode: string
  skill_mode: 'auto' | 'manual' | 'off'
  selected_skills: string[]
  status: TaskStatus
  progress: number
  current_step: string | null
  error_message: string | null
  cancel_requested: boolean
  current_revision: number
  brief_version: number
  supervisor_status: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  deleted_at: string | null
}

export interface ArchivedTask extends Task {
  memory_status: string
  archive_summary: string | null
  memory_items_count: number
  memory_last_analyzed_at: string | null
}

export interface MemoryExtraction {
  id: string
  user_id: string
  task_id: string
  status: string
  model: string
  task_summary: string | null
  habit_summary_delta: string | null
  memory_items_count: number
  attempts: number
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface UserMemory {
  id: string
  user_id: string
  category: string
  memory_key: string
  statement: string
  value_json: Record<string, unknown>
  confidence: number
  status: 'CANDIDATE' | 'ACTIVE' | 'SUPERSEDED' | 'DISABLED'
  occurrence_count: number
  source_task_id: string | null
  evidence_refs: string[]
  first_seen_at: string
  last_seen_at: string
  created_at: string
  updated_at: string
}

export interface UserMemoryProfile {
  user_id: string
  summary: string
  defaults_json: Record<string, unknown>
  version: number
  updated_at: string
}

export interface TaskEvent {
  id: number
  task_id: string
  event_type: string
  title: string
  content: string | null
  progress: number | null
  created_at: string
}

export interface TaskMessage {
  id: string
  task_id: string
  revision: number
  role: 'user' | 'assistant'
  mode: 'task' | 'chat' | 'revise' | 'revision' | 'supervisor'
  content: string
  author_user_id: string | null
  status: 'STREAMING' | 'COMPLETED' | 'FAILED'
  client_message_id: string | null
  reasoning_mode: Task['reasoning_mode'] | null
  reasoning_effort: Task['reasoning_effort'] | null
  created_at: string
}

export interface Artifact {
  id: string
  task_id: string
  node_id: string | null
  filename: string
  relative_path: string
  mime_type: string
  size: number
  is_final: boolean
  preview_kind: 'text' | 'html' | 'csv' | 'image' | 'pdf' | 'office' | 'download'
  inspection_status: string
  preview_metadata: Record<string, unknown>
  created_at: string
}

export interface Approval {
  id: string
  task_id: string
  tool_call_id: string | null
  operation: string
  summary: string
  risk: string
  arguments: Record<string, unknown>
  status: 'PENDING' | 'APPROVED_ONCE' | 'APPROVED_FOR_TASK' | 'DENIED' | 'EXPIRED'
  requested_at: string
  decided_at: string | null
  decided_by: string | null
}

export interface TaskNode {
  id: string
  task_id: string
  revision: number
  node_key: string
  role: string
  title: string
  instructions: string
  depends_on: string[]
  weight: number
  status: string
  attempt: number
  result_summary: string | null
  target_brief_version: number
  applied_brief_version: number
  started_at: string | null
  completed_at: string | null
}

export interface TaskDirective {
  id: string
  task_id: string
  message_id: string
  status: string
  kind: string
  summary: string
  affected_node_keys: string[]
  requires_replan: boolean
  applied_brief_version: number | null
  error_message: string | null
  created_at: string
  processed_at: string | null
}

export interface TaskBrief {
  id: string
  task_id: string
  version: number
  goal: string
  acceptance_criteria: string[]
  change_summary: string
  source_directive_id: string | null
  created_at: string
}

export interface TaskSupervision {
  status: string
  current_brief: TaskBrief | null
  directives: TaskDirective[]
}

export interface ToolCall {
  id: string
  task_id: string
  node_id: string | null
  tool_name: string
  status: string
  result_summary: string | null
  duration_ms: number | null
  created_at: string
  completed_at: string | null
}

export interface UsageSummary {
  prompt_tokens: number
  completion_tokens: number
  cache_hit_tokens: number
  calls: number
  duration_ms: number
}

export interface SystemConfig {
  deepseek_configured: boolean
  anysearch_configured: boolean
  model_orchestrator: string
  model_worker: string
  model_reviewer: string
  max_users: number
  max_active_tasks: number
  max_active_tasks_per_user: number
  max_agents_per_task: number
  max_global_agents: number
}

export interface Skill {
  name: string
  display_name: string
  description: string
  source: string | null
  source_ref: string | null
  supports_auto: boolean
}

export interface SkillInstallResult {
  name: string
  source: string
  source_ref: string
  installed: boolean
}

export interface SkillRemoveResult {
  name: string
  removed: boolean
  recoverable: boolean
  trash_id: string
  removed_at: string
}

export interface WorkerStatus {
  name: string
  online: boolean
  active_tasks: number
  reserved_tasks: number
}

export type ProjectRole = 'OWNER' | 'EDITOR' | 'VIEWER'

export interface Project {
  id: string
  owner_id: string
  name: string
  description: string
  is_pinned: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
  current_user_role: ProjectRole
}

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  username: string
  role: ProjectRole
  created_at: string
}

export interface ProjectFile {
  id: string
  project_id: string
  uploaded_by: string | null
  filename: string
  mime_type: string
  size: number
  version: number
  previous_version_id: string | null
  archived_at: string | null
  created_at: string
}

export interface ProjectMemory {
  id: string
  project_id: string
  category: string
  statement: string
  status: 'ACTIVE' | 'CANDIDATE' | 'DISABLED'
  source_task_id: string | null
  evidence_refs: string[]
  created_at: string
  updated_at: string
}

export interface ProjectMemoryBundle {
  profile: { project_id: string; summary: string; version: number; updated_at: string }
  items: ProjectMemory[]
}

export interface TaskSource {
  id: string
  task_id: string
  node_id: string | null
  title: string
  url: string
  domain: string
  summary: string
  source_type: string
  source_agent: string | null
  published_at: string | null
  fetched_at: string | null
  created_at: string
}

export interface SearchItem {
  kind: string
  id: string
  project_id: string | null
  task_id: string | null
  title: string
  snippet: string
  updated_at: string | null
}

export interface ArtifactPreview {
  kind: Artifact['preview_kind']
  mime_type: string
  size: number
  metadata: Record<string, unknown>
}
