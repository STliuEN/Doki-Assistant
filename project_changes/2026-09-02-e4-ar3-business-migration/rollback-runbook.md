# E4 备份、切换与 Restore-forward Runbook（草案）

日期：2026-09-02  
状态：实施中  
适用范围：E4/AR-3 业务数据迁移和唯一写权威切换  
执行状态：已授权进入准备/分批实施；真实命令仍受 allowlist、preflight、backup 和 gate 约束

## 0. 绝对前提

本 runbook 不能扩大用户已授予的范围。用户已确认 E4 计划并授权分批实施；只有在 source/target/restore allowlist、备份位置、owner/approver 和迁移开关完成 preflight 后，才可填入真实值并执行。所有命令必须拒绝默认 DSN、未登记 server UUID、E1/E2/E3 资源、在线 Django 写库、Redis/Chroma 写路径和未脱敏 source。

## 1. 批次参数（实施前填写）

| 参数 | 现值 | 责任 |
|---|---|---|
| `migration_batch_id` | `<pending>` | owner |
| source snapshot/manifest | `<pending>` | source custodian |
| target DSN/server UUID/database | `<pending>` | DBA/owner |
| restore DSN/server UUID/database | `<pending>` | recovery owner |
| source/target/restore allowlist | `<pending>` | approver |
| schema revision | 当前代码要求 `20260901_0007_e3_auth`；E4 revision 待定 | owner |
| backup location/retention | `<pending>` | recovery owner |
| stop-write window (UTC) | 不设固定时长；记录实际开始/结束时间，gate/健康检查失败即阻断 | operator |
| rollback decision authority | `<pending>` | 用户/approver |

## 2. 阶段 A：Preflight（只读）

目标：证明所有资源、版本和路径都在批准范围，且不会误连现有业务资源。

1. 将 source/target/restore 的完整 host、port、database、server UUID、容器/网络和凭证引用写入 allowlist；禁止从 `.env` 或默认值补全。
2. 执行项目现有的 preflight/guard，仅对批准的隔离资源做 `SELECT 1`、server identity、schema revision 和权限检查；不得执行业务查询或写入。
3. 记录 FastAPI、Django、runner、Redis、Chroma、Skill Storage 进程/版本和当前 active revision/generation；只读检查失败立即标 `阻塞`。
4. 对本地文件、MD5、图片和 Skill Storage 生成只读 manifest；路径必须通过 containment，符号链接/junction 拒绝。

**通过标准**：所有资源精确命中 allowlist；无隐式连接；manifest 可重放；E1/E2/E3 资源未启动、未复用、未修改。

## 3. 阶段 B：Snapshot 与 Dry-run

1. 在批准停写前先取得 source snapshot/dump；记录开始/结束 UTC、事务隔离、server UUID、schema revision、文件/Chroma manifest 和 SHA-256。
2. 对 snapshot 运行 identity-map dry-run：规范化 UUID、owner scope、唯一约束、FK、源行 digest，并输出新增/no-op/conflict/orphan 计数。
3. 使用同一 snapshot digest 生成目标导入计划；digest 漂移、未知用户、重复身份、跨用户 MD5 冲突或不可解释 orphan 均停止。
4. 将 dry-run 结果和摘要写入 `test-record.md`；不得把完整密码 hash、token、原始 IP、原始 BLOB 或未脱敏 PII 放入仓库。

**通过标准**：source/target 预期行数、digest、唯一约束和审计字段均可解释；`conflict=0`、`orphan=0` 或有用户批准的明确处置；重复 dry-run 结果稳定。

## 4. 阶段 C：隔离演练

1. 在独立 E4 target/restore fixture 中运行 additive/shadow schema 和迁移器；禁止使用 E1/E2/E3 容器、volume、network 或业务快照。
2. 重放同一批次两次，确认第二次为 no-op；修改一条 source payload，确认 digest conflict 拒绝且旧映射不变。
3. 注入 FK/唯一冲突、重复/乱序、租约过期、旧 fencing token、runner kill/restart、超时、取消和孤儿 job；验证 fail-closed、retry/DLQ 和审计 correlation。
4. 将 fixture 结果与真实等价限制分开记录；fixture 不能替代批准的 MySQL/文件/Chroma live 证据。

## 5. 阶段 D：停写与切换（需要单独授权）

1. 冻结并记录 active schema revision、migration batch、source digest、job/attempt/audit 快照和当前流量窗口。
2. 让 Django、旧脚本和文件业务入口进入只读；保留的 import/export/debug 必须显式调用并写 audit。确认没有长期双写进程。
3. 在同一 SQL UoW 中写入 canonical 业务行、`migration_maps`、FK/审计和 durable job；API 成功响应只依据 SQL commit。
4. 事务提交后由 runner 处理 Chroma/文件等派生 job；SSE/polling 从 SQL job 状态读取，Redis 只做唤醒提示。
5. 切换期间持续检查 source snapshot digest 和未登记写入；任一漂移立即停止并转阶段 F。

## 6. 阶段 E：切换后验证

- 逐表比较 source/target/restore 的行数、规范化 content digest、唯一约束、FK、时间和审计 correlation。
- 抽样验证每类 user/session/message/note/memory/knowledge/image/Skill 对象及其 owner scope；确认不存在无法解释 orphan。
- 重复请求和重复导入为幂等；乱序事件、旧 fencing token、过期 lease、kill/restart、超时、取消和异常按合同处理。
- 停止 runner 时 API readiness 仍反映 SQL 可用性，不把 Redis pending、内存队列或 Chroma 状态当业务成功。
- 保存命令、原始日志、manifest、diff、快照位置和审阅人；实现者只能提交 `待验证`。

## 7. 阶段 F：Restore-forward（失败路径）

触发条件：任何误连、source digest 漂移、唯一/FK mismatch、审计缺字段、双写、旧 token 成功提交、健康快照覆盖或回滚不可执行。

1. 立即停止 E4 runner、FastAPI 业务写入和所有迁移脚本；保留进程日志、job/attempt、audit、migration map 和错误目标，不删除 source。
2. 验证迁移前快照的 manifest、SHA-256、server UUID、schema revision、文件/Chroma manifest；不覆盖原快照。
3. 将快照恢复到独立 restore-forward 数据库/目录（目标必须在 allowlist），恢复过程使用 binary-safe 管道并保留原始日志。
4. 对恢复目标执行 schema/表/行数/content digest/唯一约束/FK/audit/correlation/migration map 对账；任何差异保持 `阻塞`。
5. 保留故障目标只读供审阅，记录 restore-forward diff 和决定；用户决定修复重试或退回，不执行 populated downgrade 或无目标删除。
6. 恢复后重新运行 API/runner smoke，确认旧 fencing token 和过期 lease 无法提交结果，再决定是否重开批次。

## 8. 关闭与后续边界

只有以下均完成且用户确认，E4 才能关闭：

- source/target/restore 对账和恢复证据完整；
- FastAPI 单一写权威抽样通过，旧写入口只读/显式运维；
- 重复/乱序、lease/fencing、kill/restart、timeout/cancel/error/orphan 覆盖通过；
- 未授权删除为零，旧输入和健康快照仍可恢复；
- 审阅人核对三件套与证据，用户明确确认关闭。

E4 关闭不自动授权 E5 RAG generation、E6 Skill 发布、E7 文件/sidecar 清理或 E8 删除/部署；这些阶段仍须单独计划和确认。

## 明确未做

- 未填写真实 DSN、server UUID、备份路径或停写时间。
- 未执行 preflight、dump、migration、停写、切换、restore-forward 或删除。
- 未将本 runbook 当作授权、回滚证据或生产运维手册。

## 清理与保留

阶段内保留所有中间测试体、失败现场和可重建材料。所有 E 编号结束并经最终验收后，统一清除原始敏感材料、临时 fixture 和可重建中间体；保留脱敏 manifest、审计、摘要、错误报告、备份和 restore-forward 证据。此规则不授权删除旧输入或未对账源。
