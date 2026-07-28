# 数据库设计

核心表：

- `users`：最多 3 个预置账号，含角色和密码哈希。
- `tasks`：主任务状态、进度、所有者和生命周期时间。
- `task_nodes`：DAG 节点、依赖、权重、角色和状态。
- `agent_runs`：每次 Agent 尝试、模型、预算和结果。
- `task_events`：只追加的用户可见事件流。
- `tool_calls`：受控工具调用及摘要。
- `artifacts`：任务产物元数据和归属。
- `approvals`：风险操作的请求、决定和审计。
- `api_usage`：模型 Token 和调用耗时。
- `user_memories`：按用户隔离的长期偏好、习惯、约束和项目约定。
- `memory_extractions`：归档任务的记忆分析状态、摘要和失败信息。
- `user_memory_profiles`：可直接注入聊天和 Agent 的紧凑使用习惯摘要。
- `memory_revisions`：记忆新增、合并、编辑、启用和停用记录。

以上表均已实现，数据库结构由 `backend/alembic/versions/0001` 至 `0012` 的迁移链管理。`0012` 为任务增加 Skill 模式和选择列表。生产环境启动 API 前必须先运行 `alembic upgrade head`，不依赖运行时自动建表。

关键约束：

- 任务、节点、Agent 尝试、审批、工具调用和产物均通过外键关联。
- `tasks.deleted_at` 实现任务软删除；文件删除由 Runner 移入任务级 `trash/`。
- `tasks.review_retries` 与配置共同限制自动返工，当前最多两次。
- 用户明确偏好可直接生效；推断习惯需要至少两次独立证据后才进入 Agent 上下文。
- `approvals.consumed_at` 防止一次性批准被重复使用。
- PostgreSQL 是持久状态和历史事件的事实来源；Redis 只负责队列、锁和实时通知。

主任务状态由程序固定：

`CREATED, QUEUED, PLANNING, RUNNING, WAITING_APPROVAL, REVIEWING, REWORKING, PACKAGING, SUCCEEDED, FAILED, CANCELING, CANCELED`

节点状态由程序固定：

`PENDING, READY, QUEUED, RUNNING, WAITING, SUCCEEDED, FAILED, RETRYING, CANCELED, SKIPPED`
