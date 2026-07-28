# MiniSwarm 修改、微调与排障说明

本文用于后续由 AI 或人工继续修改 MiniSwarm。目标是让每次调整都能回答四个问题：

1. 应修改哪一层？
2. 是否会影响数据、安全或现有任务？
3. 怎样验证修改真实有效？
4. 怎样安全发布并能够恢复？

## 1. “微调”的含义

MiniSwarm 当前没有 DeepSeek 模型权重微调接口，也没有训练数据上传、训练任务和模型版本注册系统。

本项目中的“微调”主要分为五类：

| 类型 | 调整内容 | 主要位置 |
| --- | --- | --- |
| 界面微调 | 布局、颜色、字号、交互、预览 | `frontend/src/` |
| Agent 微调 | 角色、规划、提示词、工具循环 | `backend/app/agent/` |
| 办公质量微调 | 文档结构、渲染、公式、重叠、交付门禁 | `runner/runner_app/tools.py`、`backend/app/quality.py` |
| Skill 微调 | 专业工作流和模板 | `skills/`、服务器 `/opt/miniswarm/skills/` |
| 记忆微调 | 用户偏好、项目约束、归档提取 | `backend/app/memory.py` |

只有在将来明确建设训练数据、离线评测、模型训练和模型注册后，才应把“微调”理解为模型权重训练。

## 2. 权威源码

后续修改必须以以下目录为准：

```text
frontend/       当前前端
backend/        API、Agent、数据库和 Worker
runner/         受限工具和 Office 质检
skill-manager/  Skill 安装服务
skills/         随源码管理的 Skill
docs/           设计与运维文档
compose.yaml    服务编排
```

以下位置只作历史参考：

```text
aaa/
deliverables/
deliverables/miniswarm-page-source/
.deployment/*.tar.gz
frontend/dist/
```

不要直接修改历史压缩包或 `dist`。不要从 `aaa/` 覆盖当前 `frontend/`。

## 3. 修改前检查

每次开始前先记录：

```text
目标：
复现步骤：
期望结果：
实际结果：
涉及用户：
涉及任务 ID：
是否涉及数据库迁移：
是否涉及外部网络或新依赖：
是否可能覆盖或删除数据：
```

然后执行只读检查：

1. 阅读相关源码和现有测试；
2. 查看服务健康状态和最近日志；
3. 查询任务、节点、工具调用和产物；
4. 确认问题发生在前端、API、Worker、Runner、模型还是部署层；
5. 保存一个可重复的最小测试任务。

不要因为页面提示“失败”就立即重建全部服务。先找到失败发生在哪一层。

## 4. 前端微调

### 4.1 文件定位

| 需求 | 文件 |
| --- | --- |
| 三栏工作台、项目树、右侧上下文 | `frontend/src/views/WorkbenchView.vue` |
| 新建任务和执行选项 | `frontend/src/views/TasksView.vue` |
| 旧版任务详情 | `frontend/src/views/TaskDetailView.vue` |
| 项目成员、文件和记忆 | `frontend/src/views/ProjectView.vue` |
| Skills 与安全安装 | `frontend/src/views/SkillsView.vue` |
| 归档任务 | `frontend/src/views/ArchivedTasksView.vue` |
| 全局记忆 | `frontend/src/views/MemoriesView.vue` |
| 系统管理 | `frontend/src/views/AdminView.vue` |
| 文件预览 | `frontend/src/components/ArtifactPreview.vue` |
| Markdown 渲染 | `frontend/src/components/MarkdownContent.vue` |
| 黑白主题与公共组件 | `frontend/src/styles.css` |
| 工作台响应式布局 | `frontend/src/workspace.css` |
| 路由与权限 | `frontend/src/router.ts` |
| API 请求 | `frontend/src/api.ts` |
| 类型 | `frontend/src/types.ts` |

### 4.2 视觉约定

- 支持纯白和纯黑两套主题；
- 黑色背景使用纯白正文，次要信息可用中性灰；
- 代码、工具参数和重点片段使用灰色背景，不改变正文基础字号；
- 网页设计类任务可使用蓝色提示；
- 不在全局记忆、归档和管理页残留旧蓝紫渐变；
- 正文基础字号优先保证手机可读性；
- 所有颜色通过 CSS 变量定义；
- 不在组件中随意写死白色、黑色或品牌色；
- 支持 `prefers-reduced-motion`；
- 键盘焦点必须可见。

### 4.3 交互约定

- 表单发送必须有防重复提交；
- 创建任务使用 `client_request_id`，消息使用 `client_message_id`；
- 请求失败要显示服务端 `detail`，不要统一吞成“请求失败”；
- SSE 只刷新受影响的数据区；
- 用户上翻历史时不自动拉回底部；
- 预览 iframe 内外滚动应分别测试；
- 手机、平板和桌面至少各检查一次；
- 不能只看静态截图，必须实际点击、输入、上传、滚动和返回。

### 4.4 前端验证

```powershell
Set-Location frontend
npm.cmd run typecheck
npm.cmd run build
```

涉及交互时还要验证：

- 登录与重新登录回跳；
- 创建任务；
- 任务 SSE；
- HTML/PDF/Office 预览；
- 文件上传和下载；
- 主题切换；
- 手机宽度导航；
- 管理员与普通用户权限。

## 5. Agent 微调

### 5.1 角色边界

| 角色 | 主要职责 |
| --- | --- |
| `orchestrator` | 判断复杂度、生成 DAG、分配角色 |
| `researcher` | 网络检索、来源提取和交叉核对 |
| `reader` | 读取和整理输入文件 |
| `data_analyst` | Excel、CSV、统计和图表 |
| `document` | Word、PPT、PDF 和可编辑交付 |
| `file_worker` | 文件整理、格式转换和打包 |
| `coder` | 明确的软件开发或脚本任务 |
| `reviewer` | 只读检查需求和最终文件 |

办公任务默认优先使用 `document`、`data_analyst`、`reader` 和 `researcher`。不要因为需要写一个短脚本就把整个任务归为 `coder`。

### 5.2 相关文件

- `backend/app/agent/planner.py`：计划 JSON、DAG 校验和角色标准化；
- `backend/app/agent/executor.py`：工具循环、审批、重试、产物登记；
- `backend/app/agent/deepseek.py`：模型调用、深度思考和流式响应；
- `backend/app/agent/tools.py`：模型可见工具定义；
- `backend/app/agent/skill_registry.py`：Skill 自动匹配与上下文；
- `backend/app/quality.py`：最终交付门禁；
- `backend/app/worker/tasks.py`：队列、调度、Reviewer 和状态迁移。

### 5.3 调整原则

1. 提示词只负责判断和生成内容，状态、进度、权限和文件存在性由程序负责。
2. Planner 必须输出可验证的验收条件。
3. DAG 必须无环，节点 ID 唯一，依赖真实存在。
4. 只有一个 Reviewer，并覆盖所有终端产出节点。
5. 子 Agent 不得创建下级 Agent。
6. Agent 不得自行提高轮数、工具预算、超时或并发。
7. 工具失败后应根据错误类型修正参数，不能机械重复相同调用。
8. “文件不存在”“缺少 path”“不支持文件类型”应在下一轮前程序化反馈。
9. 避免在文件生成前调用 `inspect_document`。
10. Office 二进制文件不得使用 `read_text`。

### 5.4 重要参数

```text
MAX_AGENTS_PER_TASK=8
MAX_GLOBAL_AGENTS=12
MAX_AGENT_DEPTH=1
MAX_AGENT_ROUNDS=20
MAX_REVIEW_RETRIES=2
MAX_TOOL_CALLS_PER_TASK=100
TASK_TIMEOUT_MINUTES=45
AGENT_TIMEOUT_MINUTES=20
```

修改并发前先测服务器 CPU、内存、Runner 并发和 DeepSeek 限流。不要只提高数字。

## 6. Office 专项微调

### 6.1 Word

目标：

- 标题使用真实 Heading 样式；
- 列表使用真实编号；
- 表格有明确表头和合适列宽；
- 不用空行堆版式；
- 保留可编辑 DOCX；
- 中文字体可在服务器渲染。

验证：

1. `python-docx` 能打开；
2. `inspect_document` 结构检查通过；
3. LibreOffice 转 PDF 成功；
4. 逐页渲染无空白、裁切和重叠；
5. MarkItDown 提取内容完整；
6. Reviewer 检查最终 DOCX。

### 6.2 Excel

目标：

- 公式正确且可重算；
- 数字、日期、货币和百分比格式正确；
- 列宽不会出现 `###`；
- 冻结窗格、筛选和表头清楚；
- 图表使用正确数据范围；
- 不用字符串冒充数值。

验证：

1. `openpyxl` 能打开；
2. LibreOffice 重算后保存；
3. 不存在 `#VALUE!`、`#REF!`、`#DIV/0!`；
4. 所有工作表渲染；
5. 检查截断单元格和图表残片；
6. 公式单元格与缓存值符合预期。

### 6.3 PowerPoint

目标：

- 标题、正文、图表和图片保持可编辑；
- 每页有明确视觉层级；
- 不生成大段文字墙；
- 不出现文本越界和显著重叠；
- 图片和引用来源可追踪；
- 主题、配色和字体一致。

验证：

1. `python-pptx` 能打开；
2. 文件关系和页数正常；
3. LibreOffice/Impress 渲染成功；
4. 每页生成图像并检查；
5. 文本框不超画布；
6. 可见文本框无显著重叠；
7. Reviewer 检查最终 PPTX。

Anthropic `pptx` 是服务器所有者强制安装的例外 Skill。不要把它的存在解释为可绕过 Runner；不要在未复核来源提交和风险的情况下升级。

### 6.4 PDF

优先路线：

```text
生成 DOCX -> 检查 DOCX -> convert_document -> 检查 PDF
```

直接生成 PDF 时：

- 优先使用已验证的 TTF 字体；
- 不要向 ReportLab 注册不支持的 TTC；
- 确认中文字符真实可见；
- 每页检查空白比例、黑色比例和可见文字；
- 文本层与渲染像素必须一致。

### 6.5 网络检索

深度检索建议：

1. 把问题拆成 2～5 个互补查询；
2. 优先官方机构、原始报告和一手数据；
3. 提取正文，不只保存搜索摘要；
4. 关键结论至少两个独立域名交叉验证；
5. 保存标题、机构、发布日期、访问 URL；
6. 在最终文档中写入实际 URL；
7. 区分事实、引用和模型推断。

## 7. Skill 修改与安装

常规 Skill 必须经过：

```text
官方 GitHub URL
-> 固定 commit
-> 下载/解压限制
-> 路径和符号链接检查
-> SkillSpector
-> 原子安装
```

安装结果至少保存：

- 来源仓库；
- 请求 URL；
- 固定提交；
- 扫描器版本；
- 风险分数和发现数；
- 内容 SHA-256；
- 安装时间。

当前改进项：

1. 把同步安装改成后台安装任务；
2. 增加 `QUEUED / DOWNLOADING / SCANNING / INSTALLED / REJECTED` 状态；
3. 持久化扫描报告；
4. 页面支持查看高危发现；
5. 安装完成后刷新 Skill 注册表；
6. 所有者强制放行必须单独显示并可审计。

不要覆盖已有 Skill。升级应安装到新版本目录或先完成备份、差异审查和回滚方案。

## 8. 数据库与 API 修改

### 8.1 数据库

任何模型字段变化都必须：

1. 修改 `backend/app/models.py`；
2. 创建新的 Alembic 迁移；
3. 修改 Pydantic Schema；
4. 更新 API 和测试；
5. 更新 `docs/database.md`；
6. 在生产迁移前备份数据库。

禁止：

- 在生产库手工删列；
- 删除迁移文件；
- 修改已上线迁移的 `revision`；
- 使用 `create_all` 代替迁移；
- 为解决密码问题删除 PostgreSQL 卷。

### 8.2 API

API 修改必须保持：

- 权限在服务端验证；
- 用户资源按用户或项目成员过滤；
- 管理员能力使用明确管理接口；
- 错误返回可操作的 `detail`；
- API Key 和密码不进入响应；
- 创建接口支持幂等；
- SSE 事件名称固定并可补发；
- 新接口同步更新 `frontend/src/api.ts`、`types.ts` 和 `docs/api.md`。

## 9. 当前问题修复队列

### P0

1. 恢复有效 Git 仓库和版本基线；
2. 备份并同步服务器 `skills/pptx`，记录所有者放行；
3. 核查并关闭不必要的 PostgreSQL 公网 TCP 代理；
4. 给历史成功任务区分 `LEGACY_UNVERIFIED` 或补充检查状态；
5. 为生产源码、数据库和任务卷建立可验证备份。

### P1：准确性

1. 对 `run_python` 失败按错误类型分类，优先修复路径、字体和超时；
2. 在 Executor 中阻止“输出不存在时检查”和“Office 文件用 read_text”；
3. 修复 `validate_swiss_deck` 固定工具的 4/4 失败；
4. 明确 `run_tests` 的适用任务和输入契约；
5. 统一 PDF 中文字体路线；
6. 为 XLSX 公式错误、`###` 截断建立可重复回归样本；
7. 将真实任务与质量评测任务分开统计。

### P1：安全与运维

1. 将 `skill-manager` 改为非 root UID/GID，并修正宿主机 Skills 目录权限；
2. 为 Runner/Worker 增加 egress allowlist 或代理；
3. 增加 CSRF Token 或严格 Origin 校验；
4. 锁定生产镜像 digest，停止依赖浮动 `latest`；
5. 使用域名和标准 ACME 证书替代 IP 证书；
6. 持久化 Skill 扫描和强制放行审计。

### P2

1. 更新 `docs/api.md`、`docs/database.md` 到 `0013`；
2. 增加 CI：Python 测试、前端构建、Compose 检查；
3. 增加版本号、CHANGELOG 和发布标签；
4. 处理 Starlette/httpx 弃用警告；
5. 清理源码快照混淆，但删除前必须先获得用户同意并移入回收站；
6. 建立按任务类型、版本和评测标签分层的质量仪表盘。

## 10. 测试矩阵

### 每次修改都要运行

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q

Set-Location runner
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m pytest tests -q

Set-Location ..\skill-manager
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m pytest tests -q

Set-Location ..\frontend
npm.cmd run build
```

根据修改范围增加：

| 修改范围 | 额外验证 |
| --- | --- |
| 登录/Cookie | 登录、退出、滚动续期、过期回跳 |
| SSE | 长任务、断网重连、历史补发 |
| 项目权限 | Owner/Editor/Viewer、跨用户访问 |
| 文件 | 上传、版本、归档、下载、MIME 伪装 |
| Office | 真实 DOCX/XLSX/PPTX/PDF 生成与渲染 |
| Skill | 安装、拒绝、重复安装、路径攻击 |
| 数据库 | 新库升级、现有库升级、备份恢复 |
| Agent | 单 Agent、并行 DAG、失败重试、取消 |

## 11. 发布流程

### 发布前

- 确认修改文件清单；
- 确认没有 `.env`、密码、Key、Cookie；
- 运行相关测试；
- 生成数据库备份；
- 备份 `/opt/miniswarm/skills` 和任务数据；
- 确认迁移顺序；
- 保存当前镜像或发布包。

### 发布

```text
1. 上传受影响源码
2. docker compose config
3. 构建受影响镜像
4. alembic upgrade head
5. docker compose up -d
6. docker compose ps
7. 检查 API、Worker、Runner 和 Skill Manager
8. 运行最小真实任务
```

### 发布后

- 检查 5～15 分钟关键日志；
- 检查任务创建、SSE、文件预览和下载；
- 检查数据库连接和 Worker 心跳；
- 对 Office 修改至少跑一份真实文件；
- 记录提交、发布包、迁移、测试和已知问题。

不要执行 `docker compose down -v`。不要覆盖 `.env`。不要删除任务卷或数据库卷。

## 12. 回滚原则

回滚前先判断是否包含数据库迁移：

- 纯前端：恢复上一镜像或静态资源；
- 后端无迁移：恢复上一后端镜像；
- Runner：恢复上一 Runner 镜像；
- 有迁移：先阅读迁移的 downgrade 和数据兼容性，不要盲目回滚代码；
- Skill：恢复备份目录，不覆盖现有文件；
- 数据：必须先停止写入并做当前备份。

删除、覆盖数据库、任务卷或 Skills 目录属于高风险操作。必须再次确认目标路径并获得用户同意；本机删除文件应移动到回收站。

## 13. 交给开发 AI 的提示模板

```text
你正在修改 MiniSwarm Web。

目标：
<一个明确问题>

必须先阅读：
- README.md
- fix.md
- 与问题相关的源码和测试

要求：
1. 先复现并给出证据，不猜原因。
2. 只修改解决本问题所需的最小范围。
3. 不降低路径隔离、审批、用户权限或交付门禁。
4. 不覆盖 .env、数据库卷、任务文件和 Skills。
5. 新依赖只允许来自官方可信来源，并固定版本。
6. 数据库变化必须新增 Alembic 迁移。
7. API 变化同步更新类型、前端调用和文档。
8. 修改后运行对应测试和真实场景验证。
9. 报告修改文件、测试结果、部署影响和遗留问题。
10. 未通过验证时不得声称完成。
```

## 14. 修改记录模板

```text
日期：
目标：
原因：
修改文件：
数据库迁移：
环境变量变化：
依赖变化及来源：
测试：
真实场景验证：
部署服务：
回滚方式：
遗留问题：
```

## 15. 完成标准

一次修改只有同时满足以下条件才算完成：

- 问题可复现并已消失；
- 相关自动化测试通过；
- 真实使用场景通过；
- 没有降低安全边界；
- 没有破坏旧任务和用户文件；
- 生产服务健康；
- 文档与实际行为一致；
- 明确记录未解决问题。

