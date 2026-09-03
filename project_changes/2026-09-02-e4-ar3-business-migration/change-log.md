# E4/AR-3/S3 变更日志

日期：2026-09-02  
最近更新：2026-09-03（暂停后恢复准备）  
状态：实施中  
负责人：Codex  
审阅/批准人：用户  
用户确认：2026-09-02，Q1-Q43 完成；已收到 E4 执行确认。验收确认尚未发生。

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-09-02 | `plan.md` | 新建 E4 执行计划，固化范围、入口条件、非目标、任务、风险、退出和回滚门槛 | 将 E4/AR-3 共享理解落为阶段入口；保持待确认 | 仅新增文档；未改代码、schema、配置、数据库或外部资源 | 删除本批文档，不影响运行状态 | Codex | `E4-PREP-01` |
| 2026-09-02 | `source-inventory.md` | 建立 MySQL/Django/文件/MD5/图片/Chroma/Skill/Redis source inventory 格式，记录本地只读观察和正式纳入条件 | 防止把派生投影、sidecar 或默认资源误当业务权威 | 仅记录结构和观察；未连接在线资源 | 删除本批文档 | Codex | `E4-PREP-02` |
| 2026-09-02 | `identity-map-contract.md` | 固定 source key、canonical UUID、E3 用户 UUID5 兼容、digest/幂等/conflict/orphan 状态和未决策略 | 在迁移器实现前先冻结可重放身份规则 | 仅设计合同；未写 `migration_maps` | 删除本批文档；不影响现有数据 | Codex | `E4-PREP-03` |
| 2026-09-02 | `write-path-inventory.md` | 盘点 Django、FastAPI service、Chroma/MD5/图片、Skill Storage、Redis pending、job/runner 等写入口及目标处置 | 为 FastAPI 唯一写权威和停写窗口准备清单 | 仅静态分析；未禁用或改变任何入口 | 删除本批文档 | Codex | `E4-PREP-04` |
| 2026-09-02 | `rollback-runbook.md` | 建立 preflight、snapshot、dry-run、隔离演练、停写切换、验证和 restore-forward 模板 | 确保后续实施有可执行恢复边界 | 仅模板；未填真实 DSN/路径，未执行命令 | 删除本批文档 | Codex | `E4-PREP-05` |
| 2026-09-02 | `source-inventory.md`、`plan.md`、`test-record.md` | 补记 Chroma collection/metadata 用户身份冲突、临时路径脱敏和 Skill/配置来源边界；将冲突登记为待核验项 | 防止把派生标识、环境路径或未证明来源误当作可导入事实 | 仅更新准备文档；冲突仍未解决，未生成 mapping | 删除本批文档 | Codex | `E4-PREP-06` |
| 2026-09-02 | `identity-map-contract.md`、`write-path-inventory.md`、`plan.md`、`test-record.md`、`route-match-evidence.md` | 补齐 batch/entity/artifact digest、加密配置 key、媒体 SQL 表和 reranker/calibration 权威约束；登记 `PUT /note-template/reorder` 路由冲突并保存隔离复现 | 确保唯一写权威切换不会遗漏可执行入口或不可恢复密文/媒体，也不会混淆 digest 语义 | 未修改应用代码、配置或数据；待 E4 授权后修复并验证 | 删除本批文档；运行行为未改变 | Codex | `E4-PREP-07` |
| 2026-09-02 | `plan.md`、`identity-map-contract.md`、`source-inventory.md`、`test-record.md` | 对照现有 `migration_maps` 三态 check constraint，登记 E4 流程状态与多层 digest 的 schema 兼容门槛 | 防止迁移器写入未支持状态或把不同 digest 语义混在一个字段 | 仅文档审阅；未执行 DDL、未写 mapping 或业务数据 | 删除本批文档；现有 schema 未改变 | Codex | `E4-PREP-08` |
| 2026-09-02 | `backend/app/router/note_template_router.py`、`backend/tests/test_note_template_route_matching.py` | 将具体 `PUT /note-template/reorder` 路由移到 `/{template_id}` 之前，并加入纯路由匹配回归 | 修复已登记的写入口冲突，避免静态路径被当作模板 ID | 仅改变路由注册顺序；未调用数据库或业务 API | 恢复原注册顺序（同时恢复已知缺陷）；不影响数据 | Codex | `E4-ROUTE-01` |
| 2026-09-03 | `backend/app/db/e4_guard.py`、`backend/tests/test_e4_guard.py`、`artifacts/local-inventory-v3.json` | 恢复准备后让纯 `E4Target` tuple/list 输入逐项经过同一字段校验；补记端点大小写规范化、DSN host 大小写匹配回归，并复核脱敏本地 manifest | 防止内部已解析输入绕过 allowlist 校验；为后续真实拓扑 preflight 保持 fail-closed | 仅修改守卫校验/本地测试和证据索引；未连接或写入任何业务资源 | 回退本次守卫补丁；保留 v2/v3 脱敏 manifest 作为历史证据，不影响业务数据 | Codex | `E4-PREP-09`；manifest canonical `7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac` |

## 明确未做

- 未连接、读取或修改现有业务 MySQL、Django 在线数据库、Redis 或 Chroma 服务。
- 未执行 `mysqldump`、业务 migration、Alembic populated DDL、停写、FastAPI/Django 权威切换或任何删除/GC。
- 未生成或写入 E4 `migration_maps`、业务目标表、audit/job 结果或 Chroma generation。
- 未修改业务数据访问、配置、前端、模型、数据库 schema 或外部资源；本批仅有已记录的路由修复、E4 守卫校验、inventory 工具和测试变更。
- E2/E3/E1 容器、volume、network、证据和凭证未复用、未启动、未清理。
- 本机身份未确认的 `mysqld.exe` 进程未探测、未连接、未复用；视为受保护的未知现有资源。

## 后续记录规则

每个实施变更必须关联一个 `E4-*` 任务、一个回滚点和一个证据 ID；实现完成先标 `待验证`，不得由实现者直接标 `已关闭`。任何 source digest 漂移、unknown/orphan、双写、审计缺字段或恢复失败都要单独记录为 `阻塞`。

## 清理与保留（Q22/Q34/Q43）

阶段内不清除测试体、失败现场或可重建中间材料；成功、失败、无效和历史证据均保留并单独标注。所有 E 编号阶段完成并经最终验收后，统一执行一次清理：删除原始敏感 source、临时 fixture、可重建中间体和完整环境快照；保留脱敏 manifest/inventory、审计、摘要、错误报告、备份、restore-forward 和回滚证据。旧输入、未对账源和健康快照不得因本规则提前删除。

## 本次审阅补充

- `scripts/check-docs.ps1`：`Markdown checks passed: 194 files, 178 local links.`
- 本地 route-match 复现仅使用 backend `.venv` 和合成 allowlist URL；没有建立数据库或外部服务连接。
- 用户 Q41 确认由当前执行者接手；Q42 确认按文档执行；Q43 要求沿用 E0-E3 的三件套、证据状态、restore-forward 和最终清理规则。

## 2026-09-03 暂停/恢复收口

- 上一轮按用户要求暂停并完成记录收口；本轮仅恢复 E4 准备，不进入真实业务迁移。
- `E4-PREP-09` 已完成：`22 passed`；Ruff、Python `compileall`、`git diff --check` 和文档检查均通过（`194 files, 178 local links`）。
- 本地 v3 manifest：采集时间 `2026-09-03T01:07:41.099399+00:00`，4 collections/88 embeddings、MD5 7 records/7 values、图片 0 files、Skill objects 10，2 个脱敏 `scope_conflict`。
- 工具定义的 manifest canonical digest（排除 `captured_at` 和自身摘要字段）为 `7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac`；封装 JSON 文件 SHA-256 为 `8c018624c28192a7e84000ca6b1f455d08ee57d172a6c81792d9cf7058bf7faf`，两者不可混用。
- 仍未连接 MySQL/Django/Redis/Chroma，未执行 DDL、mapping 写入、停写、切换、删除或 GC；`E4-01` 在线/正式业务部分保持 `not-run`。
- `E4-PREP-10`：身份 dry-run 将无 source metadata 的既有 target 明确归类为 `target_exists_without_mapping`，canonical UUID 显式拒绝大写；E4 guard/identity/inventory/route 定向回归 `30 passed`，相关 Ruff 检查通过。未连接真实资源。
