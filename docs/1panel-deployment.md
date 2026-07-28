# MiniSwarm Web：1Panel V2 生产部署教程

本文适用于：

- 1Panel V2；
- 单台 Linux 服务器；
- 最多 3 个账号使用；
- Docker Compose 部署；
- DeepSeek API 负责模型推理；
- 域名通过 1Panel OpenResty 反向代理到 MiniSwarm Web。

项目最终由 9 个 Compose 服务组成：

```text
frontend
api
worker-control
worker-agent
worker-memory
runner
skill-manager
postgres
redis
```

公网通常只需要开放网站的 80/443。PostgreSQL、Redis、Runner、Skill Manager 和 API 不应直接暴露到公网。如果确实使用 1Panel TCP 代理开放 PostgreSQL，应让应用继续使用 `postgres:5432`，并让 TCP 代理指向宿主机回环端口 `127.0.0.1:15432`，不要把容器动态 IP 写入 `DATABASE_URL`。

---

## 一、部署前准备

### 1. 服务器建议

最低建议：

```text
CPU：4 核
内存：8 GB
磁盘：50 GB 以上
系统：Ubuntu 22.04/24.04、Debian 12 或其他 1Panel V2 支持的 Linux
```

文档生成、多个 Agent 并行和大文件处理都会占用内存。低于 8 GB 时，建议把 `.env` 中的 `MAX_GLOBAL_AGENTS` 改为 `2` 或 `3`。

### 2. 准备域名

例如：

```text
agent.example.com
```

在域名服务商处添加：

```text
类型：A
主机记录：agent
记录值：服务器公网 IPv4
```

如果使用 IPv6，再添加 AAAA 记录。等待解析生效后，可在本地执行：

```text
nslookup agent.example.com
```

返回的 IP 应与服务器公网 IP 一致。

### 3. 防火墙和云安全组

公网建议只放行：

```text
SSH 端口：仅你的管理 IP
1Panel 面板端口：仅你的管理 IP
80/tcp：所有来源
443/tcp：所有来源
```

不要放行：

```text
5432 PostgreSQL
6379 Redis
8000 API
8080 MiniSwarm 本地入口
8100 Runner
```

`compose.yaml` 已把前端入口绑定为 `127.0.0.1:8080`，正常情况下无法从公网直接访问。

### 4. 1Panel 与 OpenResty

如果服务器还没有 1Panel，请只使用 1Panel 官方安装文档和官方安装源。安装完成后建议立即设置：

- 独立的面板端口；
- 安全入口；
- 强密码；
- MFA；
- 授权 IP；
- 面板 HTTPS。

然后在 1Panel 的「应用商店」安装官方 OpenResty。网站管理功能依赖 OpenResty。

---

## 二、把项目上传到服务器

### 方式 A：使用 1Panel 文件管理器上传

这是最适合首次部署的方式。

1. 在本地准备项目压缩包。
2. 只保留这些内容：

```text
backend/
frontend/
runner/
docs/
.env.example
.gitignore
compose.yaml
README.md
```

3. 不要打包以下开发文件：

```text
.venv/
frontend/node_modules/
frontend/dist/
data/
.git/
.agents/
*.db
```

4. 登录 1Panel，进入「主机 → 文件」。
5. 打开 `/opt`，创建目录：

```text
/opt/miniswarm
```

6. 上传压缩包并解压。
7. 最终确认服务器上存在：

```text
/opt/miniswarm/compose.yaml
/opt/miniswarm/backend/Dockerfile
/opt/miniswarm/frontend/Dockerfile
/opt/miniswarm/runner/Dockerfile
```

不要从不明网盘、第三方应用商店或随机脚本下载项目依赖。

### 方式 B：从受控 Git 仓库拉取

只有在你已把项目放入自己的可信 Git 仓库时使用。私有仓库凭证不要直接写进命令、Compose 或项目文件。

---

## 三、配置生产环境变量

### 1. 创建 `.env`

在 1Panel 文件管理器中进入：

```text
/opt/miniswarm
```

复制 `.env.example`，将副本命名为：

```text
.env
```

`.env` 已被 `.gitignore` 排除，不要提交到 Git，也不要截图发送给他人。

### 2. 生成三个独立密钥

在 1Panel「主机 → 终端」中执行以下命令，每条命令分别执行一次：

```text
openssl rand -hex 48
```

需要生成：

```text
JWT_SECRET
RUNNER_SHARED_SECRET
POSTGRES_PASSWORD
```

三个值必须彼此不同。建议数据库密码也使用十六进制随机值，避免在 `DATABASE_URL` 中遇到 URL 转义问题。

### 3. 修改 `.env`

示例结构如下。尖括号内容必须替换，不能原样保留：

```dotenv
APP_ENV=production
APP_NAME=MiniSwarm Web
API_PREFIX=/api
FRONTEND_ORIGIN=https://agent.example.com
FRONTEND_PORT=8080

JWT_SECRET=<第一个随机值>
JWT_EXPIRE_MINUTES=480
COOKIE_SECURE=true

POSTGRES_PASSWORD=<第三个随机值>
DATABASE_URL=postgresql+psycopg://miniswarm:<第三个随机值>@postgres:5432/miniswarm
REDIS_URL=redis://redis:6379/0
DATA_ROOT=/data

RUNNER_URL=http://runner:8100
RUNNER_SHARED_SECRET=<第二个随机值>

BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=

DEEPSEEK_API_KEY=<你的 DeepSeek API Key>
ANYSEARCH_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
MODEL_ORCHESTRATOR=deepseek-v4-pro
MODEL_REVIEWER=deepseek-v4-pro
MODEL_WORKER=deepseek-v4-flash

MAX_USERS=3
MAX_ACTIVE_TASKS=3
MAX_ACTIVE_TASKS_PER_USER=1
MAX_AGENTS_PER_TASK=8
MAX_GLOBAL_AGENTS=12
MAX_AGENT_DEPTH=1
MAX_AGENT_ROUNDS=20
MAX_REVIEW_RETRIES=2
MAX_TOOL_CALLS_PER_TASK=100
MAX_SKILLS_PER_NODE=3
MAX_SKILL_CONTEXT_CHARS=120000
TASK_TIMEOUT_MINUTES=45
AGENT_TIMEOUT_MINUTES=20
RUNNER_CONCURRENCY=2
MAX_UPLOAD_MB=100
MAX_TASK_STORAGE_MB=1024
```

注意：

- `FRONTEND_ORIGIN` 必须与最终访问域名完全一致，不要带末尾 `/`。
- 生产环境必须设置 `COOKIE_SECURE=true`。
- DeepSeek Key 只能放在服务器 `.env`，不要粘贴到聊天记录、截图或前端页面。
- AnySearch Key 是可选项；在 `https://anysearch.com/console/api-keys` 创建后写入 `/opt/miniswarm/.env` 的 `ANYSEARCH_API_KEY=`。留空时使用匿名低限额模式。修改后重建 Runner 并重启 API 以刷新管理页状态：`sudo docker compose up -d --force-recreate runner api`。
- `POSTGRES_PASSWORD` 与 `DATABASE_URL` 中的密码必须完全相同。
- 不要把 `BOOTSTRAP_ADMIN_PASSWORD` 写入 `.env`；后续使用交互式密码输入。

---

## 四、检查 Compose 配置

在 1Panel「主机 → 终端」执行：

```text
cd /opt/miniswarm
docker compose config
```

正确结果应输出合并后的 Compose 配置，且没有以下错误：

```text
variable is not set
invalid interpolation format
services.xxx additional properties
```

再确认镜像来源：

```text
python:3.13-slim
node:24-alpine
nginx:1.29-alpine
postgres:17-alpine
redis:8-alpine
```

这些都是 Docker Hub 官方镜像。服务器构建的 Python Dockerfile 固定使用清华大学 TUNA PyPI 镜像 `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`，前端固定使用 `https://registry.npmjs.org`。TUNA 当前没有等价的 npm Registry，因此不要使用已经停运的旧清华 npm 域名。

如果服务器不能连接 Docker Hub、PyPI 或 npm，请先解决服务器正规网络出口。不要临时添加来源不明的镜像加速器、软件仓库或安装脚本。

---

## 五、在 1Panel 创建 Compose 编排

1. 打开「容器 → 编排」。
2. 点击「创建编排」。
3. 创建方式选择「路径选择」。
4. 名称填写：

```text
miniswarm
```

5. Compose 文件选择：

```text
/opt/miniswarm/compose.yaml
```

6. 环境变量文件应与 Compose 位于同一目录：

```text
/opt/miniswarm/.env
```

7. 创建后先不要删除任何卷，也不要执行“清理未使用存储卷”。

1Panel V2 官方文档提供三种创建方式：编辑、路径选择和编排模板。本项目建议使用路径选择，以服务器上的 `compose.yaml` 为唯一配置来源。

---

## 六、首次构建与启动

### 1. 构建镜像

在终端执行：

```text
cd /opt/miniswarm
docker compose build --pull
```

首次构建会从官方来源下载镜像和依赖，可能需要数分钟。

### 2. 先启动 PostgreSQL 和 Redis

```text
docker compose up -d postgres redis
```

检查状态：

```text
docker compose ps
```

等待 `postgres` 和 `redis` 显示 `healthy`。

### 3. 执行数据库迁移

```text
docker compose run --rm api alembic -c alembic.ini upgrade head
```

迁移完成后应看到最终版本：

```text
0007_review_retry
```

不要跳过迁移，也不要在生产环境手动删除数据库表。

### 4. 启动全部服务

```text
docker compose up -d
```

### 5. 检查容器

```text
docker compose ps
```

预期看到：

```text
frontend       running
api            running / healthy
worker-control running
worker-agent   running
runner         running / healthy
postgres       running / healthy
redis          running / healthy
```

### 6. 查看启动日志

```text
docker compose logs --tail=100 api
docker compose logs --tail=100 worker-control
docker compose logs --tail=100 worker-agent
docker compose logs --tail=100 runner
```

日志中不应出现：

```text
invalid DEEPSEEK_API_KEY
password authentication failed
connection refused
RUNNER_SHARED_SECRET
```

如果日志完整打印任何密钥，应立即停止服务、更换泄露密钥并检查配置。

---

## 七、初始化管理员账号

使用交互式方式创建管理员，避免把密码写入 `.env` 或终端历史：

```text
cd /opt/miniswarm
docker compose exec api python -m app.cli bootstrap-admin
```

看到提示后输入管理员密码。密码不会显示，长度至少 12 位。

成功提示示例：

```text
管理员 admin 已创建
```

管理员只能初始化一次。如果提示账号已存在，不要删除数据库重来，直接使用已有管理员登录。

---

## 八、先做本机健康检查

在配置域名前，先在服务器终端执行：

```text
curl http://127.0.0.1:8080/api/health
```

预期返回：

```json
{"status":"ok","service":"MiniSwarm Web"}
```

再检查网页响应：

```text
curl -I http://127.0.0.1:8080/
```

预期状态码为 `200`。

如果这一步失败，先修复 Compose，不要继续配置 OpenResty。

---

## 九、在 1Panel 创建反向代理网站

1. 打开「网站」。
2. 点击「创建网站」。
3. 类型选择「反向代理」。
4. 填写：

```text
主域名：agent.example.com
代号：miniswarm
代理地址：http://127.0.0.1:8080
备注：MiniSwarm Web
```

5. 保存网站。

如果页面支持创建时直接启用 HTTPS，也可以先选择证书；否则先创建 HTTP 网站，再到网站设置中开启 HTTPS。

### OpenResty 必需配置

进入该网站的「设置 → 配置文件」，在 1Panel 生成的 HTTPS `server` 块中确认或合并以下内容：

```nginx
client_max_body_size 100m;

location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    add_header X-Accel-Buffering no;
}
```

如果 1Panel 已经生成了 `location /`，应在现有块内补充这些参数，不要再创建第二个同名 `location /`。

项目也提供了同一份片段：

```text
/opt/miniswarm/docs/openresty-miniswarm.conf
```

保存配置前使用 1Panel 的配置检查功能。不要直接覆盖整个 1Panel 生成的配置文件，只合并必要部分。

这些设置很重要：

- `client_max_body_size 100m`：允许项目设定的最大上传文件。
- `proxy_buffering off`：避免 SSE 实时事件被缓存后一次性返回。
- `proxy_read_timeout 3600s`：允许长任务保持事件连接。
- `X-Forwarded-Proto`：让应用正确识别外部 HTTPS。

---

## 十、申请并启用 HTTPS

### 1. 创建 ACME 账号

进入「网站 → 证书 → ACME 账户」，创建 Let's Encrypt、ZeroSSL 或其他 1Panel 官方支持的 ACME 账户。

### 2. 申请证书

进入「网站 → 证书 → 申请证书」。可选择：

- HTTP 验证：域名已指向服务器，80 端口可访问；
- DNS API 验证：适合通配符证书；
- 手动 DNS：需要每次手工添加解析，不适合自动续签。

建议开启自动续签。

### 3. 网站启用证书

进入 MiniSwarm 网站的「设置 → HTTPS」：

1. 选择申请好的证书；
2. 开启 HTTPS；
3. 选择 HTTP 自动跳转 HTTPS；
4. 确认 HTTPS 正常后再考虑开启 HSTS。

不要在首次验证前立刻开启长周期 HSTS；错误的证书或域名配置可能导致浏览器长时间拒绝 HTTP 回退。

---

## 十一、首次登录和功能验证

浏览器访问：

```text
https://agent.example.com
```

使用刚创建的管理员登录。

### 1. 创建另外两个账号

进入「管理」，创建两个普通账号。系统总账号数最多为 3 个。

### 2. 验证普通任务

建议按顺序测试：

1. 生成一个 TXT 文件；
2. 上传一个小型 CSV，并要求生成统计结果；
3. 生成一个简单 PDF；
4. 上传两个独立文件，观察是否创建多个 Agent；
5. 测试取消任务；
6. 测试需要覆盖文件的操作是否进入审批。

### 3. 验证隔离

用两个普通账号分别创建任务，确认：

- 用户只能看见自己的任务；
- 用户不能下载其他账号的文件；
- 每位用户同时只能运行一个主任务；
- 超出全局并发时任务进入队列。

---

## 十二、运行状态与日志

### 1. 1Panel 页面

进入「容器 → 容器」，可以查看：

- 状态；
- CPU 和内存；
- 最近日志；
- 容器详情。

### 2. 常用终端命令

```text
cd /opt/miniswarm
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 worker-control
docker compose logs --tail=200 worker-agent
docker compose logs --tail=200 runner
docker compose logs --tail=200 postgres
docker compose logs --tail=200 redis
```

实时追踪某个服务：

```text
docker compose logs -f --tail=100 worker-agent
```

停止实时追踪使用 `Ctrl+C`，不会停止容器。

---

## 十三、备份配置

生产环境至少需要备份：

```text
PostgreSQL 数据库
task_data 任务文件卷
.env（加密保存）
compose.yaml 和项目源码
```

### 1. 配置备份账号

进入「面板设置 → 备份账号」，添加可信目标，例如：

- 本地独立磁盘；
- 你的 S3/OSS/COS；
- SFTP；
- WebDAV；
- MinIO。

远端备份凭证只保存在 1Panel，不要写进项目仓库。

### 2. PostgreSQL 逻辑备份

本项目的 PostgreSQL 由 Compose 管理，不一定会自动出现在 1Panel 数据库列表中。建议在「计划任务」创建 Shell 任务，执行 `pg_dump` 逻辑备份。

先创建备份目录：

```text
/opt/miniswarm/backups/postgres
```

备份命令示例：

```text
cd /opt/miniswarm
docker compose exec -T postgres pg_dump -U miniswarm -d miniswarm -Fc > /opt/miniswarm/backups/postgres/miniswarm.dump
```

建议每天执行，然后再用 1Panel 的「备份目录」任务，把 `/opt/miniswarm/backups` 复制到远端备份账号。

如果要保留多个日期版本，应由审核过的备份脚本生成不同文件名。涉及自动删除旧备份的命令属于风险操作，启用前必须核对保留天数和目标目录。

### 3. 任务文件卷备份

先查询卷的真实路径：

```text
docker volume inspect miniswarm_task_data
```

查看输出中的 `Mountpoint`。然后在 1Panel「计划任务 → 备份目录」中选择该目录，并配置：

```text
执行周期：每天
保留份数：7 或更多
备份目标：远端备份账号
```

不要把 PostgreSQL 数据卷简单当作普通目录复制来替代 `pg_dump`。

### 4. 恢复演练

至少每月在测试环境执行一次恢复演练。备份任务显示成功，并不代表数据库和产物一定可恢复。

数据库恢复、覆盖任务卷、删除现有容器或删除存储卷均属于高风险操作。实际恢复前必须：

1. 停止用户写入；
2. 再做一份当前数据备份；
3. 核对目标服务器、数据库名和备份文件；
4. 得到管理员明确批准；
5. 优先在测试环境验证。

---

## 十四、更新项目

安全更新流程：

1. 备份 PostgreSQL、任务卷和 `.env`；
2. 上传新版本源码；
3. 不覆盖现有 `.env`；
4. 检查依赖来源和版本变化；
5. 构建新镜像；
6. 执行数据库迁移；
7. 重建服务；
8. 检查健康状态和日志。

命令顺序：

```text
cd /opt/miniswarm
docker compose config
docker compose build --pull
docker compose run --rm api alembic -c alembic.ini upgrade head
docker compose up -d
docker compose ps
```

不要使用 `docker compose down -v`。其中 `-v` 会删除数据库和任务文件卷，可能导致不可恢复的数据丢失。

数据库迁移执行后，不要假设旧代码一定能直接回滚。更新前必须保留数据库备份和上一版本源码。

---

## 十五、常见问题

### 1. 网站显示 502 Bad Gateway

先在服务器执行：

```text
curl http://127.0.0.1:8080/api/health
docker compose ps
docker compose logs --tail=100 frontend
docker compose logs --tail=100 api
```

如果本机健康检查正常但 OpenResty 仍为 502，说明反向代理地址或 OpenResty 网络方式存在差异。不要立即把数据库或 Runner 端口开放到公网。先核对 1Panel 网站代理地址和 OpenResty日志；必要时根据该服务器上 OpenResty 的实际网络模式调整代理地址。

### 2. 登录后立即退出或不断回到登录页

检查：

```text
APP_ENV=production
COOKIE_SECURE=true
FRONTEND_ORIGIN=https://实际域名
```

确认浏览器确实通过 HTTPS 访问，并清除旧域名的 Cookie 后重试。

### 3. 上传返回 413

检查 OpenResty 配置是否包含：

```nginx
client_max_body_size 100m;
```

同时确认 `.env` 中的 `MAX_UPLOAD_MB` 没有设置得更小。

### 4. 任务进度不实时，刷新后才出现

确认 OpenResty 配置包含：

```nginx
proxy_buffering off;
proxy_cache off;
add_header X-Accel-Buffering no;
proxy_read_timeout 3600s;
```

如果域名前还有 CDN，也要关闭该路径的响应缓存和流式缓冲。

### 5. Worker 显示离线

检查：

```text
docker compose logs --tail=200 worker-control
docker compose logs --tail=200 worker-agent
docker compose logs --tail=100 redis
```

常见原因：Redis 未健康、环境变量错误、Worker 启动失败或服务器内存不足。

### 6. DeepSeek 调用失败

检查：

- Key 是否有效；
- 账户是否有可用额度；
- 服务器是否能访问 `https://api.deepseek.com`；
- 模型名是否仍在 DeepSeek 官方模型列表；
- 系统时间是否准确。

不要把 Key 直接输出到日志或终端。验证配置时只检查是否为空，不打印明文。

### 7. PostgreSQL 密码错误

确认 `.env` 中：

```text
POSTGRES_PASSWORD
DATABASE_URL 中的密码
```

完全一致。注意：数据库卷第一次初始化后，再修改 `POSTGRES_PASSWORD` 不会自动修改数据库中的已有密码。不要因此删除数据库卷；应先确认数据情况，再制定密码变更方案。

### 8. 镜像或依赖下载失败

允许的默认来源：

```text
Docker Hub Official Images
https://pypi.org/simple
https://registry.npmjs.org
https://api.deepseek.com
```

不要使用搜索引擎中随机出现的安装脚本、第三方离线包、破解应用商店或来源不明的镜像。网络受限时，优先使用云服务商官方镜像缓存，或在可信机器拉取官方镜像后用 `docker save`/`docker load` 离线导入，并核对镜像 digest。

---

## 十六、上线前检查清单

### 安全

- [ ] 1Panel 已启用强密码、MFA、安全入口和授权 IP。
- [ ] `.env` 不在 Git 中，也没有发送到聊天或工单。
- [ ] 三个密钥彼此不同。
- [ ] `COOKIE_SECURE=true`。
- [ ] 公网只开放 80/443 和受限管理端口。
- [ ] 5432、6379、8000、8080、8100 未向公网开放。
- [ ] Runner 没有 Docker Socket、宿主机 root 权限和公网网络。
- [ ] 没有使用不明镜像源、npm 源或 PyPI 镜像。

### 功能

- [ ] `docker compose ps` 中所有服务正常。
- [ ] `/api/health` 返回 `ok`。
- [ ] HTTPS 证书有效并启用自动续签。
- [ ] SSE 进度实时更新。
- [ ] 管理员和两个普通账号能正常登录。
- [ ] 用户之间任务和文件相互隔离。
- [ ] 审批操作能够暂停、拒绝和恢复。
- [ ] 文档和 ZIP 文件能够下载。

### 运维

- [ ] PostgreSQL 每日逻辑备份。
- [ ] `task_data` 每日备份到独立位置。
- [ ] 远端备份账号已配置。
- [ ] 已完成至少一次测试环境恢复。
- [ ] 已设置日志和磁盘空间监控。
- [ ] 更新流程不会覆盖 `.env` 或删除卷。

---

## 官方参考

- 1Panel V2 在线安装：`https://1panel.cn/docs/v2/installation/online_installation/`
- 1Panel V2 Compose 编排：`https://1panel.cn/docs/v2/user_manual/containers/compose/`
- 1Panel V2 创建反向代理网站：`https://1panel.cn/docs/v2/user_manual/websites/website_create/`
- 1Panel V2 网站配置：`https://1panel.cn/docs/v2/user_manual/websites/website_config_basic/`
- 1Panel V2 申请证书：`https://1panel.cn/docs/v2/user_manual/websites/certificate_create/`
- 1Panel V2 计划任务与备份：`https://1panel.cn/docs/v2/user_manual/cronjobs/`
- 1Panel 官方 GitHub：`https://github.com/1Panel-dev/1Panel`
- DeepSeek API：`https://api-docs.deepseek.com/`
