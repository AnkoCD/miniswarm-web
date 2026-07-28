# MiniSwarm Web

MiniSwarm Web 是一个面向小团队（当前最多 3 个账号）的网页版云端 AI 办公工作站。浏览器负责创建任务、上传文件、查看执行过程、审批风险操作和领取结果；Linux 服务器负责调用 DeepSeek、调度 Agent、运行受限工具、保存上下文并交付 Word、Excel、PPT、PDF 等文件。

项目当前已部署在单台 Ubuntu 服务器，通过 1Panel、Docker Compose 和 OpenResty 管理。它不是通用聊天机器人，也不是宿主机远程控制工具；核心目标是让手机或电脑浏览器能够稳定完成长时间、多文件、可追踪的办公任务。

> 当前文档快照：2026-07-29。数据库最新迁移为 `0013_codex_workspace`。

## 1. 当前状态

项目已完成从单任务 Agent 原型到 Codex 风格云端工作台的主要闭环：

- 聊天、执行任务、修改文件共用同一项目会话。
- DeepSeek Planner 生成结构化 DAG，Orchestrator 选择单 Agent 或 Swarm。
- 单任务最多 8 个工作 Agent，之后由 1 个只读 Reviewer 验收；全系统最多并发 12 个工作 Agent。
- 每个 Agent 最多 20 轮模型/工具循环，单任务工具预算最多 100 次。
- 普通聊天只调用 1 个模型，不创建子 Agent。
- 任务、消息、事件、文件、来源、审批、Token 用量和全局记忆持久化到 PostgreSQL。
- SSE 支持断线补发；刷新页面不会丢失任务进度和聊天上下文。
- Runner 提供受限 Python、文件、Office、AnySearch、MarkItDown 和文档质检能力。
- Word、Excel、PPT、PDF 交付前经过结构检查、渲染和 Reviewer 检查。
- 项目空间支持 Owner / Editor / Viewer 权限、文件版本、任务归档、项目记忆和全局搜索。
- 支持纯黑/纯白主题、桌面三栏、平板抽屉和手机底部导航。

2026-07-29 的源码验证结果：

| 检查 | 结果 |
| --- | --- |
| Backend | 71 项测试通过 |
| Runner | 32 项测试通过 |
| Skill Manager | 6 项测试通过 |
| Frontend | TypeScript 检查及 Vite 生产构建通过 |
| 合计 | 109 项测试通过 |

线上服务健康检查、Skill API、项目/归档 API、数据库本地代理和核心 Worker 当前可用。

## 2. 产品工作流

### 2.1 普通聊天

```text
用户消息
  -> 读取项目上下文与启用的全局记忆
  -> 调用 1 个聊天模型
  -> 流式返回消息
  -> 分段保存到 PostgreSQL
```

普通聊天不占用工作 Agent 并发名额，适合问答、讨论、解释和任务前澄清。

### 2.2 执行任务

```text
用户要求与文件快照
  -> Planner / Orchestrator
  -> 结构化 DAG
  -> 1～8 个 Worker Agent
  -> Runner 受限工具
  -> Reviewer
  -> 程序化交付门禁
  -> 最终文件与总结
```

仅当任务至少有两个相互独立且不存在写入冲突的节点时才并行。子 Agent 只有一层，彼此不直接聊天，所有结果通过 Orchestrator 汇总。

### 2.3 修改文件

“修改文件”会在原任务中开启新修订：

1. 读取原任务对话、项目记忆和已有产物；
2. 为当前修订建立新的文件工作区；
3. 只读引用项目原文件或上一版本；
4. 生成新版本并重新检查；
5. 不覆盖用户上传的原始文件。

### 2.4 归档与记忆

任务归档不会物理删除文件。系统会把归档任务送入独立 `memory` 队列，提取用户偏好、工作习惯和长期约束：

- 明确偏好可以直接进入记忆；
- 推断习惯需要至少两次独立证据；
- 用户可以修改、启用或停用记忆；
- 全局记忆按用户隔离；
- 项目记忆只在对应项目内生效。

## 3. 系统架构

```text
Browser
   |
OpenResty / 1Panel
   |
frontend (Vue + Vant + Nginx)
   |
api (FastAPI)
   +---------------- PostgreSQL（事实来源）
   +---------------- Redis（Celery、锁、实时通知）
   |
   +-- worker-control（规划、DAG、Reviewer、交付门禁）
   +-- worker-agent（Agent 工具循环）
   +-- worker-memory（归档记忆分析）
   |
   +-- runner（受限文件、Python、Office 与检索工具）
   +-- skill-manager（GitHub Skill 下载与安全安装）
```

Compose 中有 9 个服务：

| 服务 | 职责 |
| --- | --- |
| `frontend` | Vue 静态页面、API 反向代理、SSE 转发 |
| `api` | 登录、项目、任务、文件、审批、记忆和 SSE |
| `worker-control` | 规划、节点调度、返工、Reviewer、打包 |
| `worker-agent` | 执行单 Agent 和并行子 Agent |
| `worker-memory` | 归档任务分析与记忆合并 |
| `runner` | 受限工具执行与 Office 质量检查 |
| `skill-manager` | 固定 Git 提交、下载、扫描和写入 Skill |
| `postgres` | 持久化业务状态 |
| `redis` | 队列、锁和即时通知 |

PostgreSQL 是任务状态的唯一事实来源。Redis 即使丢失即时通知，浏览器也能通过事件 ID 从数据库补回历史。

详细架构见 [docs/architecture.md](docs/architecture.md)。

## 4. 目录结构

```text
AGENT/
├─ backend/                 FastAPI、Celery、Agent、数据库与迁移
│  ├─ app/api/              HTTP API
│  ├─ app/agent/            DeepSeek、Planner、Executor、Skills
│  ├─ app/worker/           control / agent / memory 队列
│  ├─ app/quality.py        程序化交付门禁
│  ├─ app/memory.py         全局与项目记忆
│  ├─ app/models.py         SQLAlchemy 数据模型
│  ├─ alembic/versions/     0001～0013 数据库迁移
│  └─ tests/                后端测试
├─ frontend/                当前权威前端源码
│  ├─ src/views/            工作台、项目、搜索、Skills、归档、管理
│  ├─ src/components/       Markdown 和文件预览组件
│  ├─ src/workspace.css     Codex 工作台布局
│  ├─ src/styles.css        全局主题与响应式样式
│  └─ src/api.ts            前端 API 封装
├─ runner/                  受限工具、路径隔离和 Office 质检
├─ skill-manager/           Skill 下载、压缩包限制和 SkillSpector
├─ skills/                  随源码维护的 Skill
├─ docs/                    架构、API、安全、数据库和部署说明
├─ deliverables/            发布包、评测文件和 QA 证据
├─ .deployment/             服务器发布、诊断和评测辅助脚本
├─ aaa/                     早期前端微调快照，仅作参考
├─ compose.yaml             生产与本地 Compose
├─ .env.example             环境变量模板
├─ README.md                项目总览
└─ fix.md                   修改、微调、排障和交付规范
```

`frontend/` 是唯一权威前端源码。`aaa/`、`deliverables/miniswarm-page-source/` 和压缩发布包是历史快照，不应直接在其中继续开发，也不应在未核对差异时覆盖 `frontend/`。

## 5. 技术栈

### 前端

- Vue 3
- TypeScript
- Vite
- Vant
- Pinia
- Axios

### 后端和调度

- Python 3.13（项目最低声明为 3.11）
- FastAPI
- SQLAlchemy
- Alembic
- Celery
- Redis
- PostgreSQL 17
- DeepSeek API

### Runner 与办公能力

- `python-docx`
- `openpyxl`
- `python-pptx`
- `reportlab`
- `pypdf` / `pdfplumber`
- `pandas` / `matplotlib`
- MarkItDown
- LibreOffice Writer / Calc / Impress
- Poppler
- Noto CJK、文泉驿和 Liberation 字体

后端和 Runner 的 Python 依赖使用精确版本。前端依赖树由 `package-lock.json` 锁定。Runner 的 Debian/PyPI 构建使用清华 TUNA 镜像，但仍保留 Debian 官方签名验证；npm 使用官方 Registry。

## 6. 办公质量流水线

### Word / DOCX

- 优先生成真实标题样式、编号、表格和分页结构；
- 检查空文档、固定行高、标题层级和表格结构；
- 用 LibreOffice 转换为 PDF；
- 用 Poppler 逐页渲染进行视觉检查；
- Reviewer 对最终文件逐一检查。

### Excel / XLSX

- 检查工作表、公式、数值格式和冻结窗格；
- 使用 LibreOffice 重新计算公式；
- 拒绝 `#VALUE!` 等公式错误；
- 渲染全部工作表，检测 `###` 截断、单元格裁切和图表残片；
- 交付前保留可编辑 XLSX，而不是只交图片或 PDF。

### PowerPoint / PPTX

- 优先使用可编辑文本、形状和原生图表；
- 检查页数、文件关系和内容结构；
- 检测文本框超出画布和显著文本重叠；
- 生成渲染图进行视觉 QA；
- 支持 `guizang-ppt-skill`、瑞士风设计工具和 Anthropic PPTX Skill。

服务器上的 Anthropic `pptx` Skill 当前固定在提交：

```text
b29e7cf65e5cb78a5ac33d582270551bc74a14eb
```

该 Skill 曾被 SkillSpector 判定为 `84/100 · CRITICAL`，后由服务器所有者明确授权跳过门禁安装。安装记录保留了来源、提交和内容哈希。它属于服务器侧例外项，尚未同步到本地 `skills/`，后续更新必须单独复核。

### PDF

- 默认先生成可编辑 DOCX，再通过受限工具转换为 PDF；
- 直接生成 PDF 时使用已安装的中文字体；
- 逐页检测空白页、异常黑页和“有文本层但像素不可见”的情况；
- 检查页数、文本可提取性和基本版式。

### 网络检索

- AnySearch 批量检索遵守每批最多 5 个查询的官方限制；
- 深度调研应提取主要网页正文；
- 关键结论至少交叉核对两个独立来源；
- 来源标题、机构、日期和完整 URL 进入任务来源记录；
- 要求引用的交付文档必须实际包含来源 URL。

## 7. Skill 系统

任务创建时支持：

- `auto`：按任务关键词、文件类型和 Agent 角色自动选择；
- `manual`：只加载用户选择的 Skill；
- `off`：不加载 Skill。

一般安装流程：

1. 只接受公开 GitHub HTTPS 地址；
2. 拒绝查询参数、凭据、端口和路径穿越；
3. 把分支解析为具体 Git 提交；
4. 限制下载大小、文件数量和解压体积；
5. 拒绝符号链接和特殊文件；
6. 使用 NVIDIA SkillSpector 静态扫描；
7. 扫描通过后原子写入 `/skills/<name>`；
8. 已有 Skill 不自动覆盖。

Agent 只读挂载 Skill，不能修改 Skill 源目录。安装 Skill 不代表任意执行其中脚本；实际能力仍由 Runner 的固定工具和路径规则控制。

## 8. 数据模型和迁移

当前主要数据表包括：

- 用户与权限：`users`
- 项目：`projects`、`project_members`
- 项目文件与记忆：`project_files`、`project_memories`、`project_memory_profiles`
- 任务与会话：`tasks`、`task_messages`、`task_events`
- Agent：`task_nodes`、`agent_runs`
- 工具与审批：`tool_calls`、`approvals`
- 交付与来源：`artifacts`、`task_sources`
- 用量：`api_usage`
- 全局记忆：`user_memories`、`memory_extractions`、`user_memory_profiles`、`memory_revisions`

迁移链：

| 迁移 | 主要内容 |
| --- | --- |
| `0001` | 用户、任务、事件 |
| `0002` | DAG 节点、API 用量 |
| `0003` | 工具调用、审批、产物 |
| `0004` | 一次性审批消费 |
| `0005` | Agent 运行记录 |
| `0006` | 任务软删除/归档基础 |
| `0007` | Reviewer 返工次数 |
| `0008` | 模型与思考模式 |
| `0009` | 持久聊天与修订 |
| `0010` | 安全 / YOLO 自主模式 |
| `0011` | 全局记忆和归档分析 |
| `0012` | Skill 选择模式 |
| `0013` | Codex 工作台、项目、文件版本、项目记忆、来源和预览 |

生产环境只通过 Alembic 修改结构，不在应用启动时自动建表。

## 9. 配置

先复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

必须单独生成并妥善保存：

- `JWT_SECRET`
- `RUNNER_SHARED_SECRET`
- `SKILL_MANAGER_SHARED_SECRET`
- `POSTGRES_PASSWORD`
- `DEEPSEEK_API_KEY`
- 可选的 `ANYSEARCH_API_KEY`

不要把真实 `.env`、API Key、密码或 Cookie 写进源码、文档、日志和发布包。

关键能力参数：

```text
MAX_USERS=3
MAX_ACTIVE_TASKS=3
MAX_ACTIVE_TASKS_PER_USER=1
MAX_AGENTS_PER_TASK=8
MAX_GLOBAL_AGENTS=12
MAX_AGENT_DEPTH=1
MAX_AGENT_ROUNDS=20
MAX_REVIEW_RETRIES=2
MAX_TOOL_CALLS_PER_TASK=100
TASK_TIMEOUT_MINUTES=45
AGENT_TIMEOUT_MINUTES=20
```

## 10. 本地开发与验证

### 后端

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

### Runner

```powershell
Set-Location runner
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m pytest tests -q
```

### Skill Manager

```powershell
Set-Location skill-manager
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m pytest tests -q
```

### 前端

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run build
```

不要把三个 Python 测试目录在同一个 pytest 命令中直接合并；它们是独立包，未安装为 editable package 时需要各自的导入根目录。

## 11. 部署与更新

推荐部署目录：

```text
/opt/miniswarm
```

标准更新顺序：

```text
1. 备份 PostgreSQL、task_data、skills、.env 和当前源码
2. 上传新源码，不覆盖 .env
3. docker compose config
4. 构建受影响镜像
5. alembic upgrade head
6. docker compose up -d
7. docker compose ps
8. 检查 /api/health、Worker、SSE 和关键日志
9. 执行真实办公文件冒烟测试
```

严禁使用：

```text
docker compose down -v
```

它会删除数据库和任务文件卷。详细部署与 1Panel 设置见 [docs/1panel-deployment.md](docs/1panel-deployment.md)。

## 12. 安全边界

- Agent 不获得宿主机 root 权限，不挂载 Docker Socket。
- Runner 不保存 DeepSeek Key、JWT Secret 或数据库密码。
- Runner 使用 HMAC 签名、路径归一化、任务目录隔离、超时和资源上限。
- 用户输入文件只读；删除统一移动到任务回收站。
- YOLO 只放行任务目录内的可恢复操作和公开检索。
- 宿主机、路径越界、永久删除、外传用户文件仍必须拒绝。
- API 使用 HttpOnly、SameSite=Lax Cookie；生产应启用 Secure Cookie。
- 管理员没有默认项目穿透权限，必须是项目成员才能读取私人项目。

## 13. 开发过程

项目由 AI 分阶段开发，主要经历如下：

1. **需求收敛**：从“手机控制服务器 AI”收敛为 3 人使用、网页版、单服务器、小型 Agent Swarm。
2. **工程脚手架**：建立 Vue、FastAPI、PostgreSQL、Redis、Celery、Runner 和 Compose。
3. **任务闭环**：实现登录、创建任务、上传、SSE、取消、重试、产物下载。
4. **Agent 化**：接入 DeepSeek Planner、工具调用、DAG、Worker Agent 和 Reviewer。
5. **安全执行**：拆分独立 Runner，引入 HMAC、路径隔离、审批和回收站。
6. **Swarm 扩展**：从 4 个工作 Agent 扩展到单任务 8 个、全局 12 个，保持一层子 Agent。
7. **会话化**：增加聊天、上下文持久化、修订和“执行文件修改”。
8. **记忆系统**：增加任务归档、全局记忆、使用习惯摘要和归档任务查询。
9. **Codex 风格前端**：重构为三栏工作台，增加项目树、右侧上下文、移动端导航和黑白主题。
10. **项目空间**：加入项目成员权限、文件版本、项目记忆、来源和全局搜索。
11. **预览修复**：修复 HTML 预览、滚动、Office/PDF 结构预览和断线恢复。
12. **Skill 生态**：安装 AnySearch、MarkItDown、办公 Skills、Humanizer、规划与审查 Skills；增加 Skill 安装页面和 SkillSpector。
13. **办公专项优化**：强化 DOCX/XLSX/PPTX/PDF 生成、LibreOffice/Poppler 渲染、公式和布局门禁。
14. **检索专项优化**：增加 AnySearch 批量检索、正文提取、缓存、来源入库和交付引用门禁。
15. **质量评测**：建立真实 PPTX、DOCX、XLSX、PDF、调研任务和 QA 产物，持续修复失败模式。

历史发布包和 QA 证据保存在 `deliverables/`；它们用于追溯，不是权威源码。

## 14. 当前已知问题

以下数据来自 2026-07-29 的线上只读诊断。历史任务中包含主动取消、旧版本任务和刻意触发质量门禁的评测任务，因此不能直接当作最终用户失败率。

### P0：需要优先处理

1. **本地工作区缺少有效 Git 元数据**

   当前 `.git` 不能被 Git 识别，无法可靠执行 `status`、提交、回滚和差异审计。应先建立可信版本基线，不能继续只依赖压缩包覆盖。

2. **服务器与本地 Skill 状态存在漂移**

   Anthropic `pptx` 只安装在服务器，未同步到本地 `skills/`；并且它是所有者跳过 `CRITICAL` 门禁后的例外项。重建服务器、迁移目录或清理 Skills 时可能丢失。

3. **旧成功任务的 Reviewer 证据不完整**

   线上共有 25 个成功记录，其中 6 个缺少逐文件 Reviewer 检查记录。新门禁已更严格，但旧数据不应标记为完全验证。

4. **数据库公网暴露需要复核**

   Compose 仅把 PostgreSQL 绑定到 `127.0.0.1`，但服务器曾配置额外 TCP 反向代理。应确认 1Panel 和防火墙中没有继续向公网开放数据库。

### P1：交付准确性

1. `run_python` 历史调用 248 次，失败 82 次。主要原因包括路径不存在、生成脚本错误、超时和字体注册失败。
2. `inspect_document` 历史调用 133 次，失败 43 次。其中既有真实质量拦截，也有 Agent 在文件生成前检查、传错路径或检查不支持类型。
3. 瑞士风 `validate_swiss_deck` 历史 4 次调用全部失败，需要确认固定校验器路径、依赖和输入格式。
4. `run_tests` 历史 2 次调用全部失败，当前更像未完成的工具契约，不能作为可靠交付信号。
5. 仍有 Excel `#VALUE!`、单元格 `###` 截断和图表分页残片等失败样本。
6. ReportLab 对 Noto CJK 的 TTC 注册失败仍会出现在旧生成脚本中；应统一使用已验证的文泉驿字体或 DOCX 转 PDF 流程。
7. Agent 仍会产生“文件尚未创建就检查”“读取二进制 Office 文件为 UTF-8”“缺少 path 参数”等可避免调用。

### P1：前端和运维

1. Skill 安装接口为同步请求；大型仓库扫描可能持续数分钟，页面没有持久安装任务、阶段进度和历史报告。
2. Skill 安装失败只返回一次 422 Toast，详细扫描报告没有持久化到数据库，刷新后难以追踪。
3. 当前以 IP 访问为主，无域名环境下 HTTPS 信任和自动续期不如标准域名证书稳定。
4. Compose 中后端业务镜像使用 `miniswarm-backend:latest`，与“生产镜像应锁定 digest”的文档策略不完全一致。
5. `skill-manager` 为写入宿主机 Skills 目录在 Compose 中以 `0:0` 启动，虽然已移除 capabilities、启用只读根文件系统和 `no-new-privileges`，仍应改为固定非 root UID/GID 和正确目录权限。
6. Runner 与 Agent Worker 处于可出网网络；当前主要依赖工具层审批，尚无独立 egress allowlist/proxy。
7. Cookie 认证依赖 SameSite=Lax，尚未实现独立 CSRF Token 或严格 Origin 校验。
8. 本地存在 `aaa/`、多个源码压缩包和构建产物，容易让 AI 修改错误副本。

### P2：工程化

1. `docs/database.md` 和 `docs/api.md` 尚未完全覆盖 `0013` 的项目、文件、来源和预览接口。
2. 缺少可用 Git 历史、CI 流水线、版本号和正式变更日志。
3. 后端测试有 Starlette `httpx` 兼容弃用警告。
4. 当前没有模型权重微调管线、训练数据版本管理或离线评测统计平台；项目所称“微调”主要是提示词、Skill、记忆、工具和质量门禁调整。
5. 线上质量统计混合真实任务、旧版本任务和评测任务，缺少按版本、任务类型和是否评测的分层指标。

修复顺序和具体操作见 [fix.md](fix.md)。

## 15. 开发风格

本项目采用以下约定：

1. **先诊断，后修改**：先读代码、数据库状态、日志和任务证据，不凭 UI 猜原因。
2. **小步发布**：每次只解决一个明确问题，避免整套重写。
3. **数据库优先**：状态变化先写 PostgreSQL，再发送 Redis 通知。
4. **程序规则优先于模型承诺**：Agent 说“完成”不等于完成，必须通过程序化门禁。
5. **办公优先**：优先优化 Word、Excel、PPT、PDF 和网络检索，编程能力不是当前主线。
6. **可编辑交付**：能交付 DOCX/XLSX/PPTX 时，不用不可编辑图片代替。
7. **错误显式化**：保留错误摘要、工具调用和 Reviewer 证据，不吞掉失败。
8. **安全默认拒绝**：路径越界、宿主机、永久删除和外传文件默认拒绝。
9. **可信依赖**：只从官方项目或可信镜像获取，并固定版本、提交或 digest。
10. **不覆盖用户数据**：更新不覆盖 `.env`、数据库卷、任务文件卷和现有 Skill。
11. **测试伴随修改**：后端、Runner、Skill Manager 和前端各自运行对应检查。
12. **文档同步**：接口、迁移、环境变量、工具和部署行为改变时同步更新文档。

## 16. 文档索引

- [架构](docs/architecture.md)
- [API](docs/api.md)
- [数据库](docs/database.md)
- [开发说明](docs/development.md)
- [安全与审批](docs/security.md)
- [依赖来源策略](docs/dependency-policy.md)
- [Runner 办公库](docs/runner-libraries.md)
- [Codex 工作台](docs/codex-workspace.md)
- [1Panel 部署](docs/1panel-deployment.md)
- [修改与微调说明](fix.md)

## 17. 非目标

近期不计划实现：

- Kubernetes 或多服务器调度；
- 本地部署大模型；
- 多层 Agent 自我繁殖；
- 公开注册、计费和市场；
- Agent 直接控制 1Panel 或宿主机；
- 任意 Shell、Docker Socket 或 root 权限；
- 用训练模型权重代替可审计的工具和质量门禁。
