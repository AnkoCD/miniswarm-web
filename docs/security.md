# 安全与审批规则

## 无需审批的低风险操作

- 在当前任务专属目录创建新文件。
- 读取用户明确上传给该任务的文件。
- 运行已内置、无网络、有限时的只读检查器。

## 必须审批

- 覆盖输入文件或已有最终产物。
- 删除、替换或向外部服务上传文件。
- 安装系统包或未列入镜像清单的 Python/npm 包。
- 首次访问未批准的外部域名。
- 执行白名单之外的命令或提高资源/费用预算。
- 修改服务配置、端口、数据库结构或宿主机状态。

审批决定只有 `deny`、`allow_once`、`allow_for_task`。审批过期或服务重启后，不把未完成的批准推断为允许。

## YOLO 模式边界

YOLO 只自动批准 `workspace`、`shared`、`output` 中的覆盖或移动，以及公开新闻检索。它不会自动批准：

- 把文件移入回收站或永久删除；
- 修改 `input` 中的用户原始文件；
- 访问任务目录之外的路径；
- 宿主机、Docker Socket、系统配置或 root 操作；
- 把任务文件上传到外部服务。

## Runner

- 不保存 DeepSeek Key、JWT Secret 或数据库管理员密码。
- 非 root 用户运行；只挂载任务目录；只监听内部网络。
- 明确的 CPU、内存、PID、磁盘和时间限制。
- 禁止 privileged、Docker Socket、sudo、关机和宿主机敏感路径。
- 路径解析后必须仍在授权根目录中；符号链接不能越界。
- Worker 与 Runner 的请求使用独立共享密钥和 HMAC-SHA256 签名，带 60 秒防重放时间窗。

## 供应链

- 服务器构建的 Python 包从清华大学 TUNA PyPI 镜像 `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple` 下载；包名和版本仍由项目精确固定。
- npm 仅从 `https://registry.npmjs.org` 下载。
- 容器使用 Docker Official Images，并在生产部署前固定 digest。
- lock 文件必须提交；升级依赖单独审查并运行测试。

Runner 的文档库固定版本来自 PyPI 官方项目页：python-docx 1.2.0、openpyxl 3.1.5、python-pptx 1.0.2、reportlab 5.0.0、pypdf 6.14.2、Pillow 12.3.0，并额外安装 defusedxml 保护 XML 解析。
