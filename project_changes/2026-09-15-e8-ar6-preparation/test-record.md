# E8 准备测试记录

最后更新：2026-09-15；状态：`阻塞`（E8 收口前置缺口）。

| ID | 检查 | 结果 | 证据边界 |
|---|---|---|---|
| E8-P01 | E6/E7 closure index verify | 通过 | 证明 E6/E7 证据索引完整，不授权 E8 删除 |
| E8-P02 | 目标容器身份/健康状态观察 | 目标容器已恢复 healthy | 只观察指定目标；不改变 schema 或全局只读 |
| E8-P03 | 最终目标备份文件存在与 SHA 摘要 | 通过 | 备份保留；未覆盖或恢复到当前目标 |
| E8-P04 | Django、Redis、旧目录、MD5、Chroma、Skill objects 盘点 | 已记录 | 目录数量不能代替引用图或删除授权 |
| E8-P05 | new-api ID/启动时间/restart_count/status 观察 | 运行中，未操作；ID 相同、启动时间较 E6/E7 历史快照变化、restart_count 仍为 0 | 当前观察与历史 E6/E7 快照分开，不能宣称本轮未重启 |
| E8-P06 | 删除处置清单审查 | 全部 `delete_enabled=false` | 需要独立备份、对账、回滚和用户批准后才能执行 |
| E8-P07 | 运行时引用图 | 已完成，见 [dependency-map.md](./dependency-map.md) | 发现 Redis 待确认动作/ready 依赖及旧 RAG 文件路径，不能宣称已退出 |
| E8-P08 | 单机部署与恢复手册 | 候选版完成，见 [e8-runbook.md](./e8-runbook.md) | 三类副本 Smoke、RPO/RTO 和 FastAPI-only 验证仍待完成 |
| E8-P09 | 目标/Doki/Redis 运行复核 | MySQL healthy、Doki ready、runner running、Redis healthy；`new-api` running/restart_count=0 | 证明当前运行可用，不证明过渡依赖已退出 |
| E8-P10 | E8 相关代码回归子集 | **26 passed** | 仅覆盖现有健康/业务权威回归；不能证明 Redis、旧 RAG 和文件适配器已移除 |

## 收口判定

当前不能关闭 E8。阻塞项为：

1. `pending_action_store.py` 仍以 Redis 保存和一次性消费高风险待确认动作；
2. `/health/ready` 仍将 Redis 作为核心就绪条件，限流和缓存路径也未完成独立降级合同；
3. `VectorStoreService`/`MD5Store`、旧知识路径和 `skill_package_storage` 文件资源路径仍存在运行时引用；
4. FastAPI-only 三类副本 Smoke 和 RPO/RTO 尚未有 E8 自有证据；
5. 用户尚未批准逐项物理删除清单，因此所有旧资源继续 retain。

运行命令：

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e8_prepare.py
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/archive_closure.py --verify
```

E8 准备不包含真实删除、服务下线、迁移切换或生产发布测试。隔离副本上的 E6/E7 SQL-only 恢复和真实模型证据作为输入，E8 仍需自己的 FastAPI-only runbook 和三类数据库 smoke。


## E8 implementation follow-up (2026-09-15)

- E8 migration applied on the controlled target: revision 20260915_0011_e8_pending_actions; pending_actions exists.
- SQL pending action live check passed: cross-user take returned null, owner take succeeded once, repeat take returned null.
- Dedicated Redis outage check passed: /health/ready stayed HTTP 200 with degraded_optional; Redis restored with restart count 0. new-api stayed running with restart count 0.
- Full backend regression before the final default-contract correction: 537 passed, 2 failures in legacy Redis fail-closed expectations. The correction restores the default fail-closed behavior; E8 opts into degradation explicitly with REDIS_REQUIRED=false.
- Final E8 gates remain: three fixture smoke runs, RPO/RTO, SQL/Chroma/audit/FK/digest reconciliation, and per-item deletion approval.


## E8 implementation follow-up (2026-09-15)

- Target upgraded to revision 20260915_0011_e8_pending_actions; pending_actions exists; global read_only=0 and super_read_only=0.
- SQL pending action live check: cross-user read null, owner first consume succeeded, second consume null.
- Dedicated Redis outage: health remained HTTP 200 with degraded_optional; restored true 0. new-api remained true 0.
- Empty migration and restore fixture passed; 43 tables, 58 FKs, 2218 audit_events recorded; recovery about 3.75 seconds.
- Full backend regression: 539 passed, 1 warning; Ruff, compileall, diff check passed.
- Final gates passed: legacy reference audit, three fixture business smoke runs, formal RPO/RTO, and SQL/Chroma/audit/FK/digest reconciliation.


## ???????????2026-09-15?

- ????????10 ? Skill ??? 10 ? SQL package ? package digest ???10 ? legacy package migration map ?????????FK?audit_events ???? artifacts/legacy-reconciliation-20260915.json?
- ???????????19 ????17 ???9 ????18 ?????? DjangoUserService/test.sqlite3 ???????????? artifacts/legacy-test-cleanup-20260915.json?
- ???????? MySQL 127.0.0.1:33427/doki_e4??? Redis?new-api??????????? project_changes ???
- ?? Doki ???? .runtime/e8-final-dev-20260915-v2 ??????????????????????
## E8 final closure evidence (2026-09-15)

| Gate | Result | Evidence |
|---|---|---|
| Full backend regression | 539 passed, 1 warning | backend test suite |
| Current target RAG | vector/BM25/HyDE/reranker/combined/empty-owner passed | `.runtime/e8-final-dev-20260915-v2/e8-current-rag-verify.json` |
| Empty, restored, current business smoke | Passed | `.runtime/e8-empty-20260915/business-smoke.json`; `.runtime/e8-final-gates-20260915/business-smoke.json`; `.runtime/e8-current-20260915/business-smoke.json` |
| SQL/FK/package/source reconciliation | 43 tables, 58 FKs, zero checked orphans | `artifacts/e8-sql-reconciliation-20260915.json` |
| SQL-to-Chroma reconciliation | 6 owners, 12 artifacts passed | `.runtime/e8-final-gates-20260915/chroma-reconciliation.json` |
| RPO/RTO | RPO 0 committed writes lost; RTO 3.752s | `artifacts/e8-rpo-rto-20260915.json` |
| Legacy reference audit | E8 SQL-authoritative and fail-closed | `artifacts/e8-reference-audit-20260915.json` |

E8 is closed. Compatibility modules and historical resources remain retained under the documented disposition.
