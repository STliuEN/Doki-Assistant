# 826 交叉评审优先执行计划

日期：2026-08-26
状态：P0-0 至 P0-5 止血动作已落地；P0-6 未通过，当前仍停留 `AR-0 + SK-0`

本文件是 826 交叉评审的临时执行入口。`docs/architecture_rewrite_plan.md` 仍是 AR/SK 状态、依赖、队列和门禁的唯一事实源；`project_changes/2026-08-25-plan-reality-alignment/` 只提供现状与历史证据。完成本批前不得进入 AR-1，也不得解冻工作包 7-10。

## 批次与规则

执行证据目录：`project_changes/2026-08-26-change-route-execution/`

最终基线、文件归属、变更日志和测试记录分别见该目录的
`baseline.json`、`file-inventory.md`、`change-log.md` 和 `test-record.md`。

每项动作必须在 `plan.md` 登记，完成后更新 `change-log.md` 和 `test-record.md`。测试结果必须注明真实依赖、替身、基线、未覆盖风险和环境限制。不能以绿色 unit test、生成文件、目录删除或历史结果替代退出证据。

## P0 顺序

### P0-0：固定审计基线

- 基线采用当前 `HEAD + parent`：`22a009f8` / `cc9be2f3`。
- 记录完整工作树状态、纳入/排除路径、scoped diff、差异 hash 和文件归属。
- 重新核对评审报告中的 123 个业务文件，不直接复用历史数字；若发现待审业务改动或门禁受影响，立即升级为 P0。
- 补齐 08-25 批次的最终差异审查、最终检查命令和结果。

### P0-1：Chroma 失败隔离

- 移除 `backend/app/rag/vector_store.py` 初始化失败路径中的持久目录递归删除。
- 失败时保留原目录并进入 quarantine/只读状态；readiness 分开表示 API、MySQL/Redis、Storage 和 Chroma projection。
- 提供显式、带 manifest/digest 的 projection 重建入口，重建到临时位置后再切换；异常恢复不得调用通用 `reset_collection()`。
- 注入临时损坏、权限错误、版本不兼容、部分 collection 缺失和进程重启五类故障，验证原目录不变、健康快照不被破坏、projection 可恢复。

### P0-2：Skill 发布止血

- 在 `backend/app/skills/service.py`、`skill_router.py` 和 Storage 校验路径固定新导入 `installed_disabled`。
- `approve/publish/activate/rollback` 切换 active pointer 前必须重新读取 Storage 并校验 digest/元数据。
- 失败必须 fail-closed：坏包不得 READY、不得 ack 未完成事件、不得清空 Registry、不得用同 revision 的 degraded 空快照覆盖健康快照。
- 覆盖重复、超时、校验失败、digest mismatch、中断、409/413、ZIP media type、CORS 和 OpenAPI 错误合同；durable worker 留到 AR-1，不在本项提前实现。

### P0-3：MCP YAML 权威冻结

- 修改 `backend/app/agent/mcp/config.py`、`backend/app/router/mcp_router.py` 及 policy 调用边界。
- YAML 只作为 adapter/cache；在版本化 MySQL 权威尚未交付前，新增策略写入与依赖该策略的判定必须 fail-closed。
- Tool/MCP policy digest、revision、RunBinding 和迁移归属列为 AR-3/AR-5 阻断，不宣称本批已完成迁移。

### P0-4：AR-0 证据包与 R7 拆分

- 建立机器可检查的证据模板：环境、版本、拓扑、fixture、命令、阈值、实际结果、日志、负责人和批准人。
- 当前环境执行后端回归、scoped diff、失败回归和前端/browser R7；真实 MySQL/Redis/Storage/Chroma 依赖基线单独标为阻塞项。
- 真实依赖拓扑、worker 独立启动、故障注入和恢复 runbook 未具备前，不关闭 AR-0。

### P0-5：备份/恢复工具链

- 提供 MySQL、Storage、Chroma projection 的最小备份、manifest、恢复脚本和 runbook。
- 只使用隔离 fixture，不连接、不迁移、不删除或修改现有业务数据。
- 三类对象各完成一次可重复的备份、恢复、完整性校验和演练并留存证据。

### P0-6：AR-0 关口复核

- 汇总 P0-1 至 P0-5 的代码、测试、拓扑、备份和恢复证据。
- 修正 08-24 `test-record.md` 中“OpenAPI 与当前 lifecycle/错误合同一致”为“仅覆盖已实现子集”。
- 任一 P0、真实依赖拓扑或恢复证据缺失，状态保持 `AR-0`，不得宣布 `SKILL-GATE` 或 `ARCH-GATE` 通过。

## P1 并行事项

- `SKILL-GATE` 只保留单实例 worker 的 durable job、lease、fencing、重启恢复和幂等；多实例收敛移至 `PUBLIC-HA-GATE`。
- 将 R7 拆为当前环境可执行项与环境恢复后项；历史前端/真实依赖结果不作为当前证据。
- 定义授权与审计合同：角色分离、grant approve/revoke、撤销 fail-closed、correlation ID、API/worker/恢复对账和负向测试。
- 从最后包含 Legacy 目录的提交或只读备份导出 inventory/digest；建立 P0 止血对 parser/domain/outbox 提前切片的返工矩阵。

## 后续阶段

P0/AR-0 退出后才实施 AR-1 通用 durable worker、UoW、outbox、lease、heartbeat、fencing、retry、DLQ、背压和 kill/restart，并以 Skill import 为首个 consumer。之后严格按 `AR-2/3 -> AR-4/5 -> SK-5 -> SKILL-GATE -> ARCH-GATE` 执行。C 级执行和多实例公网能力不提前并入本地门禁。

## 当前验证命令

```powershell
cd backend
uv run pytest -q
uv run ruff check main.py app tests scripts
uv run python scripts/export_openapi.py --check
uv lock --check
cd ..
powershell -ExecutionPolicy Bypass -File scripts/check-docs.ps1
git diff --check HEAD^ HEAD
```

当前基线通过显式路径解析 Node 22.20.0/npm 10.9.3，前端/browser R7 已验证；真实依赖仍保持“未验证”。本批不连接或修改现有 MySQL、Redis、Chroma，不执行迁移。
