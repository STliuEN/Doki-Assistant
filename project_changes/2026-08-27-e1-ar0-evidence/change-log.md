# E1 变更日志

状态：待验证

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-08-27 | `project_changes/2026-08-27-e1-ar0-evidence/` | 建立 E1 计划、变更日志和测试记录 | 用户授权开始 E1，固定真实依赖验证边界 | 新增阶段记录，不触碰业务数据 | 删除本批新增记录；不影响运行状态 | Codex | `plan.md`、`test-record.md` |
| 2026-08-27 | Git/主机/Docker 基线 | 固定 branch、HEAD、脏工作树和工具版本 | 保证命令可复现且不把历史改动归入 E1 | 只读检查 | 无需回滚 | Codex | `test-record.md` 的 `E1-00-baseline` |
| 2026-08-27 | `backend/app/rag/vector_store.py` | 增加 Chroma 持久目录只读 preflight、collection/迁移兼容性校验、quarantine 状态和重启边界 | 防止损坏或部分 projection 在构造客户端时被隐式迁移/重建 | Chroma projection 失败闭环为 `ChromaProjectionUnavailable`；健康目录不被覆盖 | 恢复本文件并重启应用；不删除原 projection | Codex | `tests/test_chroma_containment.py`、`artifacts/logs/chroma-rebuild-attempt2.json` |
| 2026-08-27 | `backend/app/core/failed_response_register.py`、`backend/app/router/knowledge_router.py`、`backend/app/router/chat.py` | 统一 Chroma 故障 HTTP 503 envelope；stream/config mutation 在开始前 preflight；OpenAPI 声明 503 | 让查询/写入失败可诊断且 fail-closed | Chroma 不可用时不启动流、不确认成功；source list 保持独立 | 恢复路由和 handler 变更并重新生成 OpenAPI | Codex | `tests/test_chroma_http_containment.py`、`backend/openapi.json` |
| 2026-08-27 | `backend/tests/test_chroma_http_containment.py` | 新增 13 条 Chroma 相关 route 的 503、source list 例外和 OpenAPI containment 测试 | 固定 API 错误合同，覆盖非流式和流式路径 | 定向测试 30 passed（与 Chroma containment suite 合并运行） | 删除新增测试文件 | Codex | `backend/tests/test_chroma_http_containment.py` |
| 2026-08-27 | E1 隔离 MySQL `doki-e1-20260827-*` | 使用 MySQL 8.4.11 合成数据执行 dump、manifest、恢复、restore-forward 和 digest 对账 | 补齐 AR-0 真实依赖与恢复证据，不连接现有业务库 | 3 行基线恢复一致；restore-forward 后 4 行源/恢复 digest 一致 | 从只读 `mysql-bundle` 恢复到新的隔离目标 | Codex | `artifacts/logs/mysql-recovery-summary.json` |
| 2026-08-27 | E1 隔离 Chroma 目录与备份 | 执行真实写入/查询、损坏、ACL、迁移 hash、collection 缺失、重启、rebuild/quarantine | 验证 projection 可重建且失败不覆盖健康目录 | 健康语义 digest 一致；五类故障 quarantine/fail-closed；重启后 ready | 从只读 `chroma-bundle` rebuild 到新的 `fault-*` 目标 | Codex | `artifacts/logs/chroma-rebuild-attempt2.json` |
| 2026-08-27 | Storage/Chroma tamper bundles | 修改 payload 后尝试恢复 | 验证 manifest/digest 篡改不会创建目标 | 两种恢复均 exit 1，错误为 `backup payload does not match manifest`，目标不存在 | 删除隔离 tamper 副本；健康 bundle 未修改 | Codex | `artifacts/tamper-rejection/` |
| 2026-08-27 | `threat-model.md`、`characterization-matrix.md`、`platform-limitations.md` | 补齐资产/威胁、API/UI/Prompt/route 表征和跨平台限制 | 记录替身、真实依赖、未运行项和责任边界 | 只新增证据文档，不改变运行权威 | 删除本批文档；不影响代码或数据 | Codex | 三份 E1 文档 |

## 明确未做

- 未执行项目 Alembic/Django migration、统一 schema、UoW、durable runner、认证接管或业务数据迁移。
- 未连接、修改或删除现有业务 MySQL、Redis、Storage、文件、MD5 sidecar、`backend/data/chromadb` 或历史归档；E1 容器和目录均使用独立命名。
- 未下线 Django/Redis、删除旧 adapter、执行 C 级 Skill、解冻工作包 `7-10` 或声称 `SKILL-GATE`/`ARCH-GATE` 通过。
- 未修改 benchmark fixture 来放宽 Skill/Tool 授权；完整 pytest 的 schema gate 失败保留为阻塞。
- 未宣称真实 LLM/Embedding/Reranker 质量、原生 Linux/macOS、Chrome/Chromium、HA、高并发或生产 RPO/RTO 已验证。
