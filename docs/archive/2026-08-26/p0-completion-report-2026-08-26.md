# 2026-08-26 P0 收口报告

状态：P0-0 至 P0-5 已完成当前环境可执行部分；P0-6 关口复核完成，但因生产等价依赖与恢复证据缺失，继续保持 `AR-0 + SK-0`。本批未进入 AR-1，也未解冻工作包 `7-10`。

## 范围与基线

- 分支：`ai_document_assistant`。
- 固定比较：`HEAD=22a009f8b9ab16da786be6e63781775c8124ab84`，父提交 `cc9be2f3ebfffa97781f11f17a28972d7b9fe3f1`。
- 当前批次快照：34 个 tracked 修改、15 个 untracked 文件，共 49 个文件；逐文件归属、字节数和 SHA-256 见 [file-inventory.md](../../../project_changes/2026-08-26-change-route-execution/file-inventory.md)。
- 没有执行数据库迁移，没有连接、修改或删除既有 MySQL、Redis、Storage、Chroma 数据。

## P0 完成项

### P0-0：审计基线

已固定 HEAD/parent、工作树状态、tracked diff 摘要和逐文件 inventory；修正了后续 NoteService readiness 修补造成的基线漂移，并将本报告纳入批次范围。历史“123 个业务文件”未作为当前事实复用。

### P0-1：Chroma 失败隔离

初始化失败保留持久目录并进入 quarantine；readiness 分层；NoteService 使用同一投影 owner，在终态失败时返回稳定 `503`；collection reset 失败会停止重建；manifest-backed 投影重建采用 staging、digest 校验、原子切换、旧代隔离和重启栅栏。

### P0-2：Skill 发布止血

新导入固定为 `installed_disabled`；approve/publish/activate/rollback 前重验 Storage digest、manifest、metadata 和 capabilities；Storage I/O 失败隔离并映射 `503`；坏包不得 READY、ack outbox 或覆盖健康 Registry；补齐 `409/413`、ZIP media type、CORS 和 OpenAPI 合同。

### P0-3：MCP YAML 权威冻结

YAML 仅作为 adapter/cache。缺少版本化 MySQL policy authority 时，discovery/list/call/confirmation/policy write 全部 fail-closed；响应显式暴露 `policy_authority`、`status` 和 `runtime_enabled`，本地维护入口不授予运行时权限。

### P0-4：证据包与 R7

已记录环境、命令、阈值、fixture、替身、实际结果、责任人和限制。后端回归、静态检查、前端测试/lint/build 和浏览器 smoke 均在当前环境执行；真实依赖项单独标为 blocked，没有用历史结果替代当前证据。

### P0-5：备份/恢复工具链

交付离线 `mysql-dump`、`storage-tree`、`chroma-projection` bundle 工具、manifest 校验、路径穿越/符号链接/额外文件/篡改拒绝、投影重建和隔离 runbook。工具不发现或覆盖业务数据。

## 验证结果

| 检查 | 结果 |
|---|---|
| `cd backend; uv run pytest -q` | `263 passed` |
| `uv run ruff check main.py app tests scripts` | passed |
| `uv run python scripts/export_openapi.py --check` | passed |
| `uv lock --check` | passed |
| `powershell -ExecutionPolicy Bypass -File scripts/check-docs.ps1` | `154 files, 125 local links` |
| P0-1 Chroma/备份 fixture | `30 passed` |
| P0-2 Skill/API fixture | `34 passed` |
| P0-3 MCP boundary fixture | `13 passed` |
| `cd front; npm ci` | `545 packages added`，Node `22.20.0` / npm `10.9.3` |
| `cd front; npm run test` | `6 files, 28 tests passed` |
| `cd front; npm run lint -- --max-warnings 0` | passed |
| `cd front; npm run build` | passed |
| Playwright Chromium smoke | `/login` 与 `/register` 加载成功，0 个运行时错误；仅 2 个 React Router future warnings。截图见 `output/playwright/p0-login.png`、`p0-register.png` |
| `git diff --check HEAD` | passed |

## 仍未满足的 AR-0 退出条件

这些不是本批 P0 containment 的遗漏，而是退出门要求的外部证据：

1. 尚无获批的真实 MySQL/Redis/Storage/Chroma 隔离拓扑，因此未完成真实故障注入、worker 独立启动、RPO/RTO、恢复和 restore-forward 演练。
2. 统一角色分离、grant approve/revoke、撤销传播和完整审计对账属于 AR-2 合同，当前仅冻结 fail-closed 语义。
3. 跨平台依赖矩阵和生产等价容量/SLO 证据尚未建立。

## 关口决定

P0-0 至 P0-5 的代码、离线回归、当前环境 R7、备份工具和文档证据已收口。由于上述真实依赖/恢复证据缺失，P0-6 不宣布 AR-0 通过；继续保持 `AR-0 + SK-0`，不启动 AR-1，不解冻工作包 `7-10`。
