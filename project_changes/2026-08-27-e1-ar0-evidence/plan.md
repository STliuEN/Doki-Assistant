# E1 AR-0/SK-0 真实依赖与恢复证据

日期：2026-08-27  
状态：已关闭
负责人：Codex 架构重构协作代理  
审阅/批准人：用户  
用户确认：2026-08-27，用户先授权隔离环境和证据工作；技术验证提交后，用户明确要求“确认关闭 E1 并更新相关记录”，批准本批从 `待验证` 转为 `已关闭`。该关闭不授权实施 E2/AR-1。

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

- 上一阶段关闭证据：E0/S0 文档交接已关闭；本批入口阶段为 `AR-0 + SK-0`。
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
- [x] 修复离线 benchmark 的 Skill/Tool fixture 授权冲突，不放宽生产授权或让 harness 自动补 Skill。
- [x] 修复 pytest 对主应用 lifespan 和本机持久化资源的隐式依赖，并在隔离根目录复跑完整测试。
- [x] 汇总证据并将实现者状态改为 `待验证`；用户已于 2026-08-27 明确确认关闭 E1。

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
- [x] 实现者已提交 `待验证`；用户已审阅关闭结论并明确确认本批 `已关闭`。

## 回滚方案

停止 E1 测试进程和 `doki-e1-20260827-*` 容器；保留日志、dump、manifest 和隔离 volume。若隔离数据发生错误，从本批只读 bundle 恢复到新的目标并核对行数、SHA-256、Chroma collection/count 和版本。任何容器、volume 或目录清理都需再次核对名称与绝对路径，并另行获得用户确认；本次关闭不授权清理。

## 已解除阻塞与保留边界

- **完整后端 pytest**：保留首次 `280 passed, 1 failed` 和一次误连本机环境所得的无效 `282 passed` 记录。修复后 CORS 单测不启动 lifespan，pytest 在收集前强制隔离 MySQL、Redis、Django API、Skill Storage、Chroma、知识文件和日志；当前代码最终 `284 passed`，且受保护目录与应用日志未变化。误触范围和证据限制见 `test-record.md`。
- **离线 benchmark 合同**：保留首次 smoke `3/4`、regression `78/117`，以及一次行为全绿但仍触碰默认 Storage/日志的隔离失败记录。fixture 改为声明每个显式工具的最小授权 Skill，并由生产 `resolve_skills` 合同测试约束；runner 将 seed 包和日志写入结果目录。最终 smoke `4/4`、regression `117/117`，均为平均分 `1.0`、零 error/硬 veto，受保护资源未变化。
- **真实模型/Embedding/Reranker 质量**：不属于 E1 数据持久性证据，使用确定性 Embedding/脚本模型并明确标注；状态 `not-run/non-blocking`。
- **Linux/macOS 跨平台实机**：Windows 11 是唯一正式支持主机；原生 Linux/macOS 为 `out-of-scope/frozen`，不再作为 E1 或后续阶段门禁。
- **真实后端 UI E2E**：Playwright 只完成 Vite + mock/代理失败表征；E2 只验证目标 schema bootstrap/revision gate、runner 和恢复，认证成功流归 E3、业务写入归 E4、RAG 成功流归 E5。上述 E2E 均不阻塞 E1，本批也未执行 migration。
- **AR-2 授权审计闭环**：E1 只冻结并验证现有 fail-closed 合同；完整实现等待 AR-2，不作为 E1 代码交付。
- **阶段状态**：E1 技术验证没有剩余阻塞，用户已于 2026-08-27 明确确认关闭；E1/AR-0/SK-0 状态为 `已关闭`。下一阶段 E2/AR-1 仅转为 `待你确认`，本次关闭不构成 E2 实施、migration 或数据变更授权。
