from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ApprovalStatus, NodeStatus, ProjectRole, TaskStatus, ToolCallStatus, UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)
    role: UserRole = UserRole.USER


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=12, max_length=256)


class UserActiveUpdate(BaseModel):
    is_active: bool


class TaskCreate(BaseModel):
    # Chat-style tasks must accept short, meaningful messages such as “你好”.
    # The frontend already trims whitespace before sending.
    prompt: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, max_length=160)
    task_type: str = Field(default="auto", pattern="^(auto|document|code|data|file)$")
    execution_mode: str = Field(default="standard", pattern="^(standard|deep)$")
    autonomy_mode: str = Field(default="safe", pattern="^(safe|yolo)$")
    model_mode: str = Field(
        default="auto",
        pattern="^(auto|deepseek-v4-pro|deepseek-v4-flash)$",
    )
    skill_mode: str = Field(default="auto", pattern="^(auto|manual|off)$")
    selected_skills: list[str] = Field(default_factory=list, max_length=12)
    start_immediately: bool = True
    project_id: str | None = None
    project_file_ids: list[str] = Field(default_factory=list, max_length=100)
    execution_kind: Literal["auto", "chat", "task", "revision"] = "task"
    client_request_id: str | None = Field(default=None, min_length=8, max_length=64)
    web_search: bool = False


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_id: str
    project_id: str | None
    created_by: str | None
    execution_kind: str
    title: str
    prompt: str
    task_type: str
    execution_mode: str
    autonomy_mode: str
    model_mode: str
    skill_mode: str
    selected_skills: list[str]
    status: TaskStatus
    progress: int
    current_step: str | None
    error_message: str | None
    cancel_requested: bool
    review_retries: int
    current_revision: int
    brief_version: int
    supervisor_status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    deleted_at: datetime | None


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: str
    event_type: str
    title: str
    content: str | None
    progress: int | None
    created_at: datetime


class TaskList(BaseModel):
    items: list[TaskRead]
    total: int


class EventList(BaseModel):
    items: list[TaskEventRead]
    last_event_id: int


class TaskMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    mode: Literal["auto", "chat", "revise", "task"] = "chat"
    client_message_id: str | None = Field(default=None, min_length=8, max_length=64)
    execution_mode: str | None = Field(default=None, pattern="^(standard|deep)$")
    web_search: bool = False


class TaskMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    revision: int
    role: str
    mode: str
    content: str
    author_user_id: str | None
    status: str
    client_message_id: str | None
    created_at: datetime


class TaskDirectiveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    message_id: str
    status: str
    kind: str
    summary: str
    affected_node_keys: list[str]
    requires_replan: bool
    applied_brief_version: int | None
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None


class TaskBriefRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    version: int
    goal: str
    acceptance_criteria: list[str]
    change_summary: str
    source_directive_id: str | None
    created_at: datetime


class TaskSupervisionRead(BaseModel):
    status: str
    current_brief: TaskBriefRead | None
    directives: list[TaskDirectiveRead]


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    tool_call_id: str | None
    operation: str
    summary: str
    risk: str
    arguments: dict
    status: ApprovalStatus
    requested_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    consumed_at: datetime | None


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(deny|allow_once|allow_for_task)$")


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    node_id: str | None
    filename: str
    relative_path: str
    mime_type: str
    size: int
    is_final: bool
    preview_kind: str
    inspection_status: str
    preview_metadata: dict
    brief_version: int
    created_at: datetime


class TaskNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    revision: int
    node_key: str
    role: str
    title: str
    instructions: str
    depends_on: list[str]
    weight: int
    status: NodeStatus
    attempt: int
    result_summary: str | None
    target_brief_version: int
    applied_brief_version: int
    started_at: datetime | None
    completed_at: datetime | None


class ToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    node_id: str | None
    tool_name: str
    status: ToolCallStatus
    result_summary: str | None
    duration_ms: int | None
    created_at: datetime
    completed_at: datetime | None


class UsageSummary(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    calls: int
    duration_ms: int


class SystemConfigRead(BaseModel):
    deepseek_configured: bool
    anysearch_configured: bool
    model_orchestrator: str
    model_worker: str
    model_reviewer: str
    max_users: int
    max_active_tasks: int
    max_active_tasks_per_user: int
    max_agents_per_task: int
    max_global_agents: int


class WorkerStatusRead(BaseModel):
    name: str
    online: bool
    active_tasks: int
    reserved_tasks: int


class SkillRead(BaseModel):
    name: str
    display_name: str
    description: str
    source: str | None = None
    source_ref: str | None = None
    supports_auto: bool = True


class SkillInstallRequest(BaseModel):
    url: str = Field(min_length=19, max_length=2048)


class SkillInstallRead(BaseModel):
    name: str
    source: str
    source_ref: str
    risk_score: int
    risk_severity: str
    recommendation: str
    finding_count: int
    scan_mode: str
    installed: bool


class SkillRemoveRead(BaseModel):
    name: str
    removed: bool
    recoverable: bool
    trash_id: str
    removed_at: datetime


class ArchiveTaskRead(TaskRead):
    memory_status: str
    archive_summary: str | None = None
    memory_items_count: int = 0
    memory_last_analyzed_at: datetime | None = None


class ArchiveTaskList(BaseModel):
    items: list[ArchiveTaskRead]
    total: int


class ArchiveResponse(BaseModel):
    task: TaskRead
    memory_extraction_id: str
    memory_status: str


class MemoryExtractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    task_id: str
    status: str
    model: str
    task_summary: str | None
    habit_summary_delta: str | None
    memory_items_count: int
    attempts: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class UserMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    category: str
    memory_key: str
    statement: str
    value_json: dict
    confidence: float
    status: str
    occurrence_count: int
    source_task_id: str | None
    evidence_refs: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class UserMemoryList(BaseModel):
    items: list[UserMemoryRead]
    total: int


class UserMemoryProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    summary: str
    defaults_json: dict
    version: int
    updated_at: datetime


class UserMemoryUpdate(BaseModel):
    statement: str | None = Field(default=None, min_length=2, max_length=2000)
    category: str | None = Field(
        default=None,
        pattern="^(preference|habit|constraint|workflow|format|correction|project)$",
    )
    confidence: float | None = Field(default=None, ge=0, le=1)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10_000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=10_000)
    is_pinned: bool | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_id: str
    name: str
    description: str
    is_pinned: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_user_role: ProjectRole | None = None


class ProjectList(BaseModel):
    items: list[ProjectRead]
    total: int


class ProjectMemberCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    role: ProjectRole = ProjectRole.VIEWER


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberRead(BaseModel):
    id: str
    project_id: str
    user_id: str
    username: str
    role: ProjectRole
    created_at: datetime


class ProjectFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    uploaded_by: str | None
    filename: str
    mime_type: str
    size: int
    version: int
    previous_version_id: str | None
    archived_at: datetime | None
    created_at: datetime


class ProjectMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    category: str
    statement: str
    status: str
    source_task_id: str | None
    evidence_refs: list[str]
    created_at: datetime
    updated_at: datetime


class ProjectMemoryUpdate(BaseModel):
    statement: str | None = Field(default=None, min_length=1, max_length=4000)
    category: str | None = Field(default=None, min_length=1, max_length=32)
    status: Literal["ACTIVE", "CANDIDATE", "DISABLED"] | None = None


class ProjectMemoryProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    project_id: str
    summary: str
    version: int
    updated_at: datetime


class ProjectMemoryBundle(BaseModel):
    profile: ProjectMemoryProfileRead
    items: list[ProjectMemoryRead]


class TaskSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    node_id: str | None
    title: str
    url: str
    domain: str
    summary: str
    source_type: str
    source_agent: str | None
    published_at: datetime | None
    fetched_at: datetime | None
    created_at: datetime


class SearchItem(BaseModel):
    kind: str
    id: str
    project_id: str | None = None
    task_id: str | None = None
    title: str
    snippet: str
    updated_at: datetime | None = None


class SearchResult(BaseModel):
    items: list[SearchItem]
    total: int
    limit: int
    offset: int


class ArtifactPreviewMetadata(BaseModel):
    kind: str
    mime_type: str
    size: int
    metadata: dict
