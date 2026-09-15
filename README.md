# Doki Assistant

Doki Assistant 是本地 AI Agent 工作台，提供对话、知识库、笔记、记忆、Skill/Tool、模型和 MCP 能力。

## E8 最终状态

截至 2026-09-15，E8/AR-6 已关闭。本次大规模重构在本地单机范围内完成 SQL 权威迁移、RAG 投影、恢复演练和最终门禁。

当前事实边界：

- MySQL 是业务唯一权威；用户、会话、消息、笔记、Skill、权限、任务、审计、generation 和 pending action 均以 SQL 为准。
- Chroma 是由 SQL generation 重建的 owner-scoped 投影，不是业务事实来源。
- Redis 仅用于可选缓存和限流；它不能承载业务事实。
- 旧 Vector、MD5、文件路径和 Skill adapter 保留为兼容/维护路径，但 E8 业务路径不会回退到它们，并在边界处 fail-closed。
- new-api 为 observe-only；本次未修改、未重启。
- MySQL 全局 read_only/super_read_only 保持 0/0，避免影响主机其他服务。

E-number 的目标是架构精简与本地业务闭环；生产部署能力和历史资源物理删除不属于本项目目标，也不是 E8 缺口。

## 本地服务

| 服务 | 地址 | 角色 |
|---|---|---|
| 前端 | http://127.0.0.1:18080 | React/Vite |
| FastAPI | http://127.0.0.1:18000 | API、SSE、RAG |
| MySQL | 127.0.0.1:33427/doki_e4 | 业务权威 |
| Redis | 127.0.0.1:18020 | 可选缓存/限流 |
| Ollama | http://127.0.0.1:11434 | 本地模型 |

执行迁移或恢复时，只能使用 allowlist 指定的 loopback 目标；不要连接主机 3306、设置全局只读或影响 new-api。

## 验证

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
backend\.venv\Scripts\ruff.exe check backend\app backend\ops backend\tests
backend\.venv\Scripts\python.exe -m compileall -q backend
```

E8 证据：后端 539 passed；三类业务 smoke 通过；六条 RAG 分支通过；SQL 43 表/58 FK 对账通过；6 owner/12 artifact 的 SQL→Chroma 对账通过；RPO 为 0，RTO 为 3.752 秒；/health/ready HTTP 200。

## 文档

- [文档索引](docs/README.md)
- [目标架构](docs/architecture-target-blueprint-2026-08-26.md)
- [架构重写计划](docs/architecture_rewrite_plan.md)
- [执行交接](docs/architecture-execution-handoff-2026-08-26.md)
- [E8 运行手册](project_changes/2026-09-15-e8-ar6-preparation/e8-runbook.md)
- [E8 最终判定](project_changes/2026-09-15-e8-ar6-preparation/artifacts/e8-final-decision-20260915.json)
