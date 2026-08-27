# E1 AR-0/SK-0 真实依赖与恢复证据

日期：2026-08-27  
状态：待验证  
负责人：Codex 架构重构协作代理  
审阅/批准人：用户  
用户确认：2026-08-27，用户允许进行更改并明确要求开始 E1；该确认授权隔离环境和证据工作，不代表阶段关闭。

## 目标

- 在全新、隔离、可识别的 MySQL 8.x 与 Chroma 持久化拓扑上补齐 AR-0 的真实依赖证据。
- 复跑 P0-1 至 P0-5，并对真实 Chroma 执行损坏、权限、版本不兼容、collection 缺失和进程重启故障验证。
- 对隔离 MySQL、Chroma projection 和受保护输入执行备份、恢复、完整性校验与 restore-forward 演练。
- 补齐 API/UI/Prompt/route characterization、威胁边界、跨平台限制和可复现证据。

## 非目标

- 不进入 AR-1，不设计或实现统一 schema、UoW、durable job 或内置 runner。
- 不运行项目 Alembic migration，不迁移、删除、覆盖或连接现有业务 MySQL、Redis、Storage、文件或 Chroma 数据。
- 不切换认证、业务写权威或权限模型，不删除 Django/Redis/旧 adapter，不解冻工作包 `7-10`。
- 不把确定性 Embedding/模型测试桩、fixture 或绿色单元测试解释为真实模型质量或生产门禁证据。

## 依赖与入口条件

- 上一阶段关闭证据：E0/S0 文档交接已关闭；主计划仍为 `AR-0 + SK-0`。
- 固定代码基线：分支 `ai_document_assistant`，HEAD `d0b882683111adee4d6edfcec4d085cadf14a42a`；已有脏工作树由用户保留，本批不清理、不覆盖。
- 主机：Windows 11 64-bit build 26100、PowerShell 5.1、Python 3.12.3、uv 0.8.17、Docker Engine 29.5.3。
- 隔离拓扑：新建 `doki-e1-*` Docker 资源和本批专用目录；MySQL 仅绑定 loopback；Chroma 使用项目锁定的真实运行库和新持久目录。
- 备份位置：`project_changes/2026-08-27-e1-ar0-evidence/artifacts/backups/`；只保存本批合成数据和可重建 projection。
- 停写和迁移开关：不存在业务写入；项目 migration、真实业务连接和旧依赖删除保持禁用。

## 任务清单

- [x] 建立 E1 三份阶段记录，写明 owner、approver、授权范围、拓扑和保护边界。
- [x] 固定 Git HEAD、分支、脏工作树和主机/Docker 基线，不重写历史批次。
- [x] 建立并记录隔离 MySQL 8.x、真实 Chroma 持久目录、确定性 Embedding 测试桩和证据目录。
- [x] 复跑 P0-1 至 P0-5 与当前工作树回归，区分 fixture、真实依赖和未覆盖项。
- [x] 执行 MySQL 合成数据的 dump、manifest bundle、恢复、行数/digest 对账和 restore-forward。
- [x] 执行真实 Chroma 正常写入/查询、五类故障注入、进程重启、备份恢复和原目录保护验证。
- [x] 补齐 API/UI/Prompt/route characterization、威胁模型、跨平台限制和审计关联记录。
- [x] 汇总证据并将实现者状态改为 `待验证`；用户确认关闭仍未完成。

## 风险与保护

- 不得修改/删除：现有 Docker 容器和 volume、现有 MySQL/Redis、仓库既有 `data/`、`chromadb/`、Storage、文件/MD5 sidecar、历史备份和用户脏工作树。
- 本批资源使用唯一 `doki-e1-20260827-*` 名称、loopback 端口和专用路径；命令执行前后核对解析路径与资源标签。
- MySQL、Chroma 或 manifest/digest 校验失败即 fail-closed；不得用空目录重建覆盖健康 projection。
- 真实依赖行为与 P0 合同冲突时停止对应路径，保留快照与日志，修复仅限 P0/安全/数据完整性/启动阻断范围。
- 退出或回滚优先 restore-forward；不自动清理证据资源，避免误删和证据丢失。

## 退出条件

- [x] 真实 MySQL/Chroma 拓扑、版本、端口、路径和责任边界已记录。
- [x] P0 回归和五类 Chroma 故障均有命令、阈值、实际结果和日志。
- [x] MySQL、Chroma 与受保护输入的备份、恢复、digest/行数校验和 restore-forward 已演练。
- [x] 原 Chroma 目录与健康 projection 未被失败路径覆盖；查询失败语义符合 `degraded/503` 合同。
- [x] characterization、威胁边界、真实依赖与替身限制已注明（见 `threat-model.md`、`characterization-matrix.md`、`platform-limitations.md`）。
- [x] 实现者已提交 `待验证`；审阅人检查和用户确认关闭尚未完成。

## 回滚方案

停止 E1 测试进程和 `doki-e1-20260827-*` 容器；保留日志、dump、manifest 和隔离 volume。若隔离数据发生错误，从本批只读 bundle 恢复到新的目标并核对行数、SHA-256、Chroma collection/count 和版本。任何容器、volume 或目录清理都需再次核对名称与绝对路径，并在阶段关闭后由用户确认。

## 未完成与阻塞

- **完整后端 pytest**：`280 passed, 1 failed`。唯一失败 `test_skill_import_idempotency_header_is_allowed_by_cors` 需要真实主应用 lifespan；当前数据库 schema revision 不满足 `20260824_0002`。E1 禁止 migration，也不能连接既有 `localhost:3306` 业务 MySQL，保持 `blocked`。
- **离线 benchmark 合同**：smoke 4 cases 为 3 passed/1 error；regression 117 cases 为 78 passed/39 errors，集中在 `skill_tool_selection`/`tool_safety` 将 `skill_ids=["memory_write"]` 与未获该 Skill 授权的 `delete_memory` 等工具同时传入。需明确 fixture/Skill 合同后再修复，保持 `blocked`，本批不放宽授权。
- **真实模型/Embedding/Reranker 质量**：不属于 E1 数据持久性证据，使用确定性 Embedding 测试桩并明确标注，后续在线质量门禁另行验证，状态 `not-run`。
- **Linux/macOS 跨平台实机**：当前仅有 Windows 主机与 Docker Linux 内核；缺失平台保持 `not-run`，不能由路径 fixture 替代。
- **真实后端 UI E2E**：Playwright 仅完成 Vite + mock/代理失败表征；真实业务后端因 schema gate 未启动，状态 `blocked`。
- **AR-2 授权审计闭环**：合同可 characterization，完整实现必须等待 AR-2，不作为 E1 代码交付，状态 `not-run`。
