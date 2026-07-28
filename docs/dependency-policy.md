# 依赖来源与版本策略

## 允许的来源

- Python：PyPI 官方项目，通过清华 TUNA PyPI 镜像获取固定版本。
- Debian 系统包：Debian 官方仓库内容，通过清华 TUNA Debian 镜像获取并验证 Debian 官方签名。
- JavaScript：仅 `https://registry.npmjs.org`。
- 基础镜像：Docker Official Images。
- DeepSeek 协议和模型名：仅 DeepSeek 官方 API 文档。

## 固定版本

Python 的直接依赖在 `backend/pyproject.toml` 和 `runner/pyproject.toml` 中使用精确版本；前端完整依赖树由 `frontend/package-lock.json` 锁定。构建后应保存镜像 digest，生产更新不得使用未经测试的浮动 `latest` 标签。

当前 Skill/适配器来源记录：

- AnySearch：`anysearch-ai/anysearch-skill`，`v3.0.1`。
- Humanizer-zh：`op7418/Humanizer-zh`，固定提交见目录来源文件。
- Open Code Review：`alibaba/open-code-review/skills/open-code-review`，固定提交见目录来源文件。
- MarkItDown：`microsoft/markitdown`；Runner 固定安装 `markitdown[all]==0.1.6`，本项目提供受控 Skill 适配器。
- Skill Creator：`anthropics/skills/skills/skill-creator`，固定提交见目录来源文件。
- Planning With Files：`OthmanAdi/planning-with-files/skills/planning-with-files`，固定提交见目录来源文件。
- DOCX、PDF、XLSX：`anthropics/skills` 中对应目录，三项固定到同一官方提交，详见各目录 `.miniswarm-source.json`。

## 更新流程

1. 在官方项目页核对版本、维护者、Python/Node 兼容性和安全公告。
2. 单独修改版本，不混入业务功能改动。
3. 从官方源安装并运行后端、Runner、文档生成和前端构建测试。
4. 在测试服务器构建容器并记录镜像 digest。
5. 备份数据库后才升级生产环境。

禁止在 Agent 运行期间动态安装包。新增支持库属于风险操作，必须由管理员批准并通过镜像重建加入。
