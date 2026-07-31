# API 约定

统一前缀为 `/api`，认证使用 `HttpOnly`、`SameSite=Lax` Cookie。生产环境必须启用 HTTPS 和 `Secure` Cookie。

## 当前接口

- `GET /api/health`：健康检查。
- `POST /api/auth/login`：登录并设置 Cookie。
- `POST /api/auth/logout`：清除 Cookie。
- `GET /api/auth/me`：当前用户。
- `PUT /api/auth/password`：修改当前用户密码。
- `GET /api/admin/system`：管理员查看脱敏系统配置。
- `GET /api/admin/users`：管理员查看账号。
- `POST /api/admin/users`：管理员创建账号，系统总数最多 3 个。
- `PUT /api/admin/users/{id}/password`：管理员重置密码。
- `PUT /api/admin/users/{id}/active`：管理员启用或停用账号。
- `GET /api/admin/workers`：管理员查看 Celery Worker 在线和负载状态。
- `GET /api/skills`：返回已安装 Skill 的名称、说明和来源，不返回任何密钥。
- `POST /api/skills/install`：管理员直接添加公开 GitHub Skill；安全校验、提交固定和原子安装在服务端完成。
- `DELETE /api/skills/{name}`：管理员移除 Skill；目录会进入服务器 Skill 回收区，不会永久删除。
- `POST /api/tasks`：可通过 `execution_mode=deep` 开启深度思考；`web_search=true` 会在聊天中执行一次明确授权的联网检索，任务模式则把联网要求写入执行上下文。
- `POST /api/tasks/{task_id}/messages`：支持 `execution_mode` 与 `web_search`，用于当前消息的思考和联网选项。
- `execution_kind=auto` 与消息 `mode=auto`：由 DeepSeek 根据指令和任务状态自动选择聊天、执行任务或修改文件；模型不可用或判断无效时保守回退为聊天。
- `GET /api/tasks`：仅返回本人任务，管理员可用 `all_users=true` 查看全部。
- `POST /api/tasks`：创建任务草稿；除模型、思考和自主模式外，`skill_mode` 支持 `auto`、`manual`、`off`，`selected_skills` 保存用户选择；手动模式至少选择一项。
- `GET /api/tasks/{id}`：任务详情。
- `GET /api/tasks/{id}/messages`：读取持久化任务对话。
- `POST /api/tasks/{id}/messages`：发送 `chat` 消息，或用 `revise` 开启新修订并继续修改任务文件。
- `GET /api/tasks/{id}/supervision`：读取 Supervisor 状态、当前 Task Brief 与运行中要求。
- `POST /api/tasks/{id}/files`：向尚未开始的任务上传文件。
- `POST /api/tasks/{id}/start`：投递任务。
- `POST /api/tasks/{id}/cancel`：请求取消。
- `POST /api/tasks/{id}/retry`：从失败/取消状态重新排队。
- `POST /api/tasks/{id}/archive`：软归档任务并异步整理全局记忆。
- `DELETE /api/tasks/{id}`：兼容入口，执行相同的软归档流程。
- `GET /api/tasks/archived`：查询、筛选和分页读取本人归档任务。
- `GET /api/tasks/archived/{id}`：归档任务摘要与记忆整理状态。
- `POST /api/tasks/{id}/restore`：恢复归档任务。
- `GET /api/tasks/{id}/archive-analysis`：查询归档记忆分析状态。
- `POST /api/tasks/{id}/archive-analysis/retry`：重试失败或未执行的归档分析。
- `GET /api/tasks/{id}/events`：分页读取历史事件。
- `GET /api/tasks/{id}/stream`：SSE；支持 `Last-Event-ID`。
- `GET /api/tasks/{id}/nodes`：DAG 节点及状态。
- `GET /api/tasks/{id}/tool-calls`：工具调用审计摘要。
- `GET /api/tasks/{id}/usage`：模型调用与 Token 汇总。
- `GET /api/tasks/{id}/approvals`：审批请求列表。
- `POST /api/tasks/{id}/approvals/{approval_id}`：拒绝、允许一次或本任务内允许。
- `GET /api/tasks/{id}/artifacts`：任务产物列表。
- `GET /api/tasks/{id}/artifacts/{artifact_id}/download`：按归属校验后下载产物。
- `GET /api/tasks/{id}/artifacts/{artifact_id}/preview`：预览受支持的文本产物。
- `GET /api/memories`：查询当前用户的全局记忆。
- `GET /api/memories/profile`：读取当前用户的使用习惯摘要。
- `PATCH /api/memories/{id}`：修改记忆内容、类别或置信度。
- `POST /api/memories/{id}/activate`：确认并启用记忆。
- `POST /api/memories/{id}/disable`：停用记忆，不物理删除记录。

## SSE 事件

每条事件含数据库递增 ID。事件名称固定，例如 `task.created`、`task.planning`、`plan.created`、`agent.started`、`agent.progress`、`approval.required`、`artifact.created`、`task.completed` 和 `task.failed`。客户端先补读数据库历史，再订阅实时事件；模型内部推理不会作为事件返回。

活动任务对 `mode=auto` 的消息会异步进入 Supervisor。API 立即返回已持久化消息，随后通过 `supervisor.received`、`supervisor.classified`、`brief.updated`、`directive.applied` 或 `directive.needs_clarification` 更新状态。

## 安全约定

- 所有用户资源接口均在服务端校验所有权，管理员跨用户查看只允许在明确的管理接口中发生。
- API Key 不进入任何响应；错误信息和工具结果会做长度限制与敏感信息清理。
- Runner 不对公网开放，只接受带时间戳的 HMAC 签名内部请求。
- 风险操作必须先获得未过期、未消费且作用域匹配的批准。
