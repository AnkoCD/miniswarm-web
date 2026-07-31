# 系统架构

## 边界

系统面向 3 个预置账号，部署在单台 Linux 服务器。模型推理由 DeepSeek API 完成，本机负责调度、工具执行、文件处理和交付。

```text
Browser -> OpenResty -> frontend / api
                         |
                   PostgreSQL + Redis
                         |
 control / planner / supervisor / chat / agent / memory workers
                         |
              isolated runner / skill manager
                         |
                  per-task workspace
```

## 服务职责

- `frontend`：移动端优先的 Vue 页面。
- `api`：认证、任务、文件、审批和 SSE。
- `worker-control`：短状态事务、DAG 调度、汇总和恢复投递。
- `worker-planner`：初始计划和结构化 DAG 生成。
- `worker-supervisor`：运行中消息分类、版本化 Brief 和安全检查点合并。
- `worker-chat`：流式聊天，避免长回复阻塞调度。
- `worker-agent`：执行单 Agent 或子 Agent 工具循环。
- `runner`：无模型密钥的受限执行服务，不对公网开放；只读挂载已审查 Skill，并提供固定的 Skill 读取、模板复制、AnySearch、MarkItDown 和瑞士风 HTML 校验工具。
- `skill-manager`：独立下载和扫描服务，不持有模型密钥、数据库密码或任务数据；只接受公开 GitHub HTTPS 地址，固定提交后运行 NVIDIA SkillSpector，扫描通过才写入 Skill 目录。
- `postgres`：用户、任务、节点、事件、调用和产物的事实来源。
- `redis`：Celery broker、临时锁、并发信号量和实时通知。

## Swarm 约束

- 只有 Orchestrator 可创建子任务。
- 最大深度为 1；子 Agent 之间不直接通信。
- 模型产生结构化 DAG，程序负责依赖检查、幂等投递和重试。
- 只有至少两个独立节点且无写冲突时才启用并行。
- Reviewer 默认只读，自动返工次数由 `MAX_REVIEW_RETRIES` 控制，生产默认最多 3 次。
- Planner 必须输出客观验收条件；DAG 校验保证唯一 Reviewer 覆盖全部终端产出节点。
- 所有节点完成后仍需通过程序化交付门禁：显式或办公默认格式、文件存在性与大小、调研来源数量/域名/正文提取、交付物来源 URL、逐文件检查记录缺一不可。
- DOCX 由 LibreOffice 转为 PDF 后逐页渲染，同时检查真实标题/编号、表格和固定行高风险；XLSX 会先由 LibreOffice 重新计算，再扫描公式错误并渲染全部工作表；PDF 直接逐页渲染并拒绝空白页和异常黑页。
- PPTX 检查不只验证文件结构和页数，还会拒绝超出画布的文本框以及显著相交的可见文本框，促使生产 Agent 自动返工。
- 每任务最多 12 个工作 Agent，全系统最多并发 16 个；单任务同时运行最多 8 个，聊天和 Supervisor 不占工作 Agent 配额。
- 活动任务中的新要求先持久化为 directive；当前模型或工具调用不中断，Worker 在下一安全检查点接收 Brief 增量。
- Reviewer 必须按最新 Brief 验收；存在待处理 directive 或节点尚未应用最新版本时不得交付。
- YOLO 是任务级自主模式，不改变 Agent 数量：只对任务目录内可恢复操作和公开检索自动授权；删除、用户输入文件、宿主机和路径隔离边界不可绕过。

## Skill 加载

- Skill 源文件位于 `/skills/<skill-name>`，只读挂载到 `worker-agent` 与 `runner`。
- 只有 `skill-manager` 对 Skill 目录具有写权限；它拒绝凭据化 URL、非 GitHub 来源、路径穿越、符号链接、超限压缩包和覆盖已有 Skill。
- 用户可选择 `auto`、`manual` 或 `off`；自动模式按任务关键词与节点角色选择，手动模式只加载用户选择项，关闭模式不加载 Skill。
- Executor 只向模型暴露当前节点已启用 Skill 对应的工具，并限制单节点 Skill 数量和总上下文长度。
- Agent 只能通过固定工具读取 Skill 文本、复制单个模板/资源；不能修改 Skill 源目录，也不能执行其中任意命令。
- 瑞士风 HTML 仅能调用固定的官方 `validate-swiss-deck.mjs`，Runner 不提供任意 Shell。
- AnySearch 只运行固定的官方 Node CLI；安全模式下联网需审批，API Key 仅由 Runner 环境变量读取。结构化结果会递归提取并保存为来源，深度调研要求主要来源正文提取和交付物 URL 可追溯。
- MarkItDown 只转换当前任务目录内的文件，结果只能写入 `workspace`、`shared` 或 `output`。
- Anthropic DOCX/PDF/XLSX Skill 提供格式和质量工作流；执行时只使用 Runner 已固定的 Python 文档库。LibreOffice 与 Poppler 只能由 `inspect_document` 的固定只读质检流程调用，Agent 不能运行任意 Shell 或动态安装。

## 事件一致性

业务状态与事件先写 PostgreSQL，再发布 Redis 通知。浏览器重连时携带最后事件 ID；API 先补发数据库历史，再继续等待新事件，因此 Redis 丢消息不会丢业务进度。

前端对 SSE 事件做 550 ms 合并，并按事件类型只刷新任务、消息、产物、节点、工具、来源或用量中的相关部分。消息流只有在用户位于底部附近时自动跟随，避免长任务进度打断阅读。

Supervisor 使用 `supervisor.*`、`directive.*` 和 `brief.updated` 事件报告接收、分类、澄清、合并与应用状态。PostgreSQL 仍是事实来源，Redis 只负责队列和即时通知。
