# E6/E7 Skill、权限与联合收口

E6/E7 已于 2026-09-15 纳入联合收口。Skill package、version、installation、grant、run binding、registry、审计和任务状态均以 SQL 为准。

当前结果：

- 10 个历史包已迁入 SQL，稳定 ID/digest 保留。
- 本地 Skill 按授权状态运行。
- 外部 MCP Skill 为 unsupported/disabled，不能绕过授权。
- pending action 和 durable job 状态存 SQL。
- 兼容 Skill adapter 保留为维护路径，E8 业务不会隐式回退。

任何重新迁移或权限变更都必须使用新隔离 fixture、备份、allowlist 和审计记录，不得使用全局只读或影响 new-api。E8 final decision 是当前最终门禁。
