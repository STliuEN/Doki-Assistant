# E6/E7 联合批次变更日志

状态：`已关闭`（2026-09-15）；用户要求 E6/E7 伴生执行并完成剩余缺口，新安全管理员已按指定名字创建。最终记录见 [closure-review.md](./closure-review.md)。

| 日期 | 变更 | 原因与影响 | 证据 / 回退 |
|---|---|---|---|
| 2026-09-14 | E5 追加明确关闭确认和 E6/E7 联合启动记录 | 记录最新用户指令；旧 E5 技术判定/已封存结果保持历史时间边界 | E5 user-closure-confirmation-20260914.json、stage-transition.json |
| 2026-09-14 | 新联合 plan/contracts/test-record 与三份主文档同步 | E6/E7 共属 AR-5，以接口依赖替代“E6 先整阶段关闭”的串行入口 | 当前文档 diff；旧文档在 E5 baseline ZIP |
| 2026-09-14 | 新 `backend/ops/e6_e7/prepare.py` 及 README | 精确 target SELECT/SHOW、文件 digest/parser 校验、E5 基线封存；不改运行数据 | preparation.json 与私有清单；移除新工具可回退，SQL 无改动 |
| 2026-09-14 | 105 项准备回归＋文档/Ruff/diff 检查 | 识别可复用切片与尚未实现门槛，固定联合迁移的起点 | baseline-tests.json、checks.json |

以上为准备时快照，不代表后续执行范围。E5 的未提交工作树及历史材料完整保留，没有创建 commit。

| 2026-09-14 | Completed E6/E7 0010 schema, SQL Skill package/upload migration, and target installation disablement | Established SQL authority while preserving four-eyes boundary; no target grant was auto-approved | `.runtime/e6e7-target-20260914/target-migration.json` |
| 2026-09-14 | Completed replica media and four-eyes authorization acceptance | Owner/source checks, corruption rejection, request/approval/revoke/expiry/drift fail-closed | `.runtime/e6e7-login-replica-20260914/media-acceptance.json`, `authorization-acceptance.json` |
| 2026-09-14 | Final joint decision | E6/E7 implemented but not closed; blocked by target independent security_admin, approved grants, and real target media positive evidence | `artifacts/e6-e7-final-decision.json` |

以上早期未关闭判定已由 2026-09-15 证据取代，详见收口文档中的更正说明。

| 日期 | 最终变更 | 结果 |
|---|---|---|
| 2026-09-14/15 | 新建 `STliuEN-security-admin`、验证角色分离、完成 8 项 grant 与 lifecycle 启用 | 密码/API/浏览器有效；2 个外部 MCP 保持 unsupported |
| 2026-09-15 | 补真实 SQL 正负例、Run/tool/job/resource/confirmation 撤销、媒体 ingest/隔离/恢复 | 旧泛化异常和无正向控制证据被严格断言取代 |
| 2026-09-15 | 新空库迁移、42 表 SQL-only 恢复、新 Chroma、固定端口重启 | 包/图文/授权/审计恢复，revoked Run 不复活，new-api 不变 |
| 2026-09-15 | 修复首轮对话父会话与绑定事务；SQL 健康检查退出旧磁盘依赖 | 本机模型实际调用工具并保存 SSE；回归 539/29、lint/build 通过 |
| 2026-09-15 | E6/E7 联合关闭；文档及代码/证据索引归档 | E8 和全局门禁保持冻结 |

Target backup, old objects, sidecar, failed inputs, and replica evidence remain retained. MySQL global read-only was not changed, host 3306 was not used, and `new-api` was not modified or restarted.

