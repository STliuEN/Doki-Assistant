# E2/AR-1/S1 变更日志

状态：待你确认

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-08-28 | `project_changes/2026-08-28-e2-ar1-sql-foundation/` | 新建 E2 `plan.md`、`change-log.md`、`test-record.md`、`schema-map.md` 和只读 SQL 盘点 | 补齐 E2 在进入 `待你确认` 前缺失的批次边界、schema ownership、合同、环境和证据占位 | 仅文档和静态盘点；未创建容器、未改 schema/代码、未连接数据库 | 删除本批新增文档；不影响运行状态 | Codex | `E2-PREP-01` 至 `E2-PREP-04`、`E2-PREP-07` |
| 2026-08-28 | `README.md`、`project_changes/README.md`、`docs/architecture_rewrite_plan.md` | 同步 E1 已关闭、E2 待确认和本批入口链接 | 根 README 仍保留 2026-08-25 的“当前停留 AR-0”旧口径；活计划尚未链接 E2 批次 | 仅文档状态入口；E2 仍未获实施授权 | 恢复对应文档行 | Codex | `E2-PREP-02`、`E2-PREP-04` |
| 2026-08-28 | `docs/stage-execution-record-template-2026-08-26.md` | 将证据状态统一为四个值，并把失败/无效/fixture 类型拆到“结果/处置” | 防止 E1 式证据状态继续漂移 | 仅后续记录格式；不重写 E1 历史事实 | 恢复模板变更 | Codex | `E2-PREP-03` |
| 2026-08-28 | 准备批次验证 | 运行现有 SQL/migration/transaction/backup 定向测试、文档检查和 diff check | 确认准备基线可重复且本批没有代码/schema 变更 | `45 passed`；Markdown `182 files, 163 local links`；`git diff --check` exit 0 | 无运行状态变更；测试均为 tmp_path/SQLite/source tree | Codex | `E2-PREP-05`、`E2-PREP-06` |

## 明确未做

- 未创建、启动、停止或修改 E2/E1 Docker container、volume 或 network。
- 未读取 `backend/.env`、`DjangoUserService/.env`，未连接现有或隔离 MySQL/Redis/Chroma/Storage。
- 未修改 backend 业务代码、SQLAlchemy model、Alembic revision、schema 或 `DATABASE_SCHEMA_REVISION`。
- 未执行 `alembic upgrade/downgrade/stamp`、`mysqldump`、SQL import、数据迁移、停写或删除。
- 未把准备工作解释为 E2 实施授权、`待验证`、`已关闭`、`SKILL-GATE` 或 `ARCH-GATE` 通过。
