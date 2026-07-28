# Runtime Skills

此目录在部署时挂载到 API、Worker、Runner 和 Skill Manager。

第三方 Skill 源文件不提交到本仓库，原因包括：

- 部分 Skill 使用专有许可证，不允许复制或再分发；
- 生产服务器需要保存固定提交、扫描结果和内容哈希；
- Skill 更新应独立于应用源码发布。

标准安装方式：

1. 在 MiniSwarm 的 Skills 页面提交公开 GitHub HTTPS 地址；
2. 系统把分支解析为固定提交；
3. 检查下载大小、文件数量、路径和符号链接；
4. 使用 NVIDIA SkillSpector 扫描；
5. 扫描通过后原子安装到 `/skills/<name>`。

生产备份必须单独包含：

```text
/opt/miniswarm/skills
```

服务器所有者强制放行的 Skill 必须保留独立审计记录，不应仅依赖本仓库恢复。
