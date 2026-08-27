# 2026-08-26 Grill-me 审阅结果参考清单

状态：`参考资料`（不属于当前事实源，不授权迁移、删除、部署或发布）  
整理日期：2026-08-26

## 1. 来源与使用规则

本清单整理自前序 `$grill-me` 讨论中确认的 q1-q92 决策，以及同期的[改动路线审阅报告](./change-route-review-2026-08-26.md)。仓库没有保存原始对话导出，因此本文是可追溯的归并摘要，不声称逐字复现原始会话。

当前执行时仍只认：

- [架构重写计划](../../architecture_rewrite_plan.md)：阶段状态、依赖、门禁和当前队列的唯一事实源。
- [最终重构蓝图](../../architecture-target-blueprint-2026-08-26.md)：目标架构和阶段交付边界。
- [执行交接手册](../../architecture-execution-handoff-2026-08-26.md)：E/S/AR 映射、停线、证据和回滚规则。

本清单与当前计划冲突时，以以上三个入口为准。审阅结论被纳入文档合同，不等于对应代码、真实依赖或门禁已经完成。

## 2. Grill-me 决策已吸收项

| 主题 | 已吸收的结论 | 当前文档位置 | 状态 |
|---|---|---|---|
| 部署范围 | 单机、小范围局域网、低并发；不以前置公网、HA、多实例为目标。 | 蓝图 §1；主计划 §1 | 已纳入，未做部署验收 |
| 业务权威 | 一个 MySQL 实例/数据库承载业务事实；FastAPI 最终成为唯一写入口。 | 蓝图 §1-2；主计划 §4 | 已纳入，迁移未执行 |
| RAG | 保留 Chroma 原生向量检索；SQL 保存原文和配置，不保存向量 BLOB；Chroma 可从 SQL 重建。 | 蓝图 §1、§3；交接手册 E5 | 已纳入，真实重建未验证 |
| 认证与会话 | users/sessions/refresh/revocations/roles/audit 进入 SQL；Redis 不参与正确性；Django 仅过渡适配。 | 蓝图 §2、§4；交接手册 E3 | 已纳入，AR-2 未实现 |
| 角色和授权 | 内容/Skill 管理员与安全管理员分离；`grant approve` 与 `grant revoke` 分离；撤销传播 fail-closed；完整审计字段固定。 | 主计划 §5；交接手册 E3 | 合同已纳入，闭环未实现 |
| 任务执行 | SQL durable job + 内置 runner，默认并发 1；支持 lease、fencing、重试、DLQ 和重启恢复。 | 蓝图 S1/AR-1；交接手册 E2 | 已纳入，AR-1 未实现 |
| Skill | 兼容 Codex 风格根目录 `SKILL.md` 的目录/ZIP；新导入 `installed_disabled`；A/B 保留，C 级返回 `unsupported`。 | 蓝图 §1；交接手册 E6 | 已纳入，Skill 迁移未实现 |
| 过渡依赖 | Redis、Django、文件/MD5 sidecar、旧 Skill 结构和旧 Chroma generation 仅迁移期保留，完成对账和恢复后删除。 | 蓝图 §1-2；交接手册 E7-E8 | 已纳入，删除未执行 |
| 发布冻结 | 架构收敛、恢复验收和核心回归关闭前，冻结新功能、工作包 7-10、公网、HA 和 C 级执行。 | q92；主计划 §6、§8 | 已纳入并生效 |

q85-q92 已在[最终重构蓝图的确认记录](../../architecture-target-blueprint-2026-08-26.md#q85-q92-确认记录)中逐项列出；q1-q84 的决定已归并到上述边界和合同，未逐题建立独立编号表。

## 3. 路线审阅发现 C1-C14 对照

| 编号 | 审阅发现 | 新体系中的承接位置 | 当前状态 |
|---|---|---|---|
| C1 | Chroma 初始化失败会破坏性删除持久目录。 | P0-1；E1 故障注入；Chroma `degraded/503`、staging 重建和原目录保护。 | 合同和当前环境止血已纳入；真实故障/恢复证据待 E1。 |
| C2 | Skill import/publish 非持久、非原子，缺 durable worker。 | P0-2；E2 SQL runner；E6 Skill 导入、digest、重启恢复和幂等。 | `installed_disabled` 和 fail-closed 已纳入；实现和真实恢复待 E2/E6。 |
| C3 | 工作树和变更批次不可审计。 | 阶段记录模板、批次 `change-log/test-record`、E1 基线固定规则。 | 本次交接文档基线已记录；AR-0 完整逐文件归属和真实依赖基线仍待确认。 |
| C4 | MCP/Tool policy 仍由本地 YAML 充当权威。 | YAML 仅 adapter/cache；AR-3/AR-5 的 SQL revision/digest/RunBinding 和迁移阻断。 | 边界已冻结；SQL 权威迁移未实现。 |
| C5 | 门禁缺少命令、拓扑、阈值、证据格式和批准人。 | 阶段记录模板、E1-E8 证据表、`SKILL-GATE`/`ARCH-GATE` 规则。 | 文档规格已纳入；真实证据尚未齐全。 |
| C6 | R7 前置与当前环境存在死锁。 | 将当前环境 fixture/文档检查与真实依赖恢复拆分；E1 只做基线和故障证据，不实现 durable runner。 | 已纳入执行路径。 |
| C7 | 本地 SKILL-GATE 混入多实例要求。 | 本地门只验单实例；多实例收敛移至 `PUBLIC-HA-GATE`。 | 已纳入门禁边界。 |
| C8 | P0 止血可能影响提前落地的 Skill/parser/domain/outbox 切片。 | 模板保留“受影响的提前切片及返工范围”；E1 退出材料要求记录返工影响。 | 约束已纳入；逐模块影响矩阵仍待 E1。 |
| C9 | 备份/恢复工具链没有明确归属。 | P0-6/E1 备份、恢复、完整性校验和 restore-forward；E2-E8 复用证据。 | 离线工具和规则已纳入；真实 MySQL/Chroma 恢复演练待 E1。 |
| C10 | 08-24 test-record 对已实现 Skill 合同表述过度。 | 所有阶段记录必须区分 fixture、历史日志和真实依赖，不能用绿色测试替代门禁。 | 证据措辞规则已纳入；历史报告保留为追溯，不作为当前完成证据。 |
| C11 | Legacy 迁移输入具有时间敏感性，旧目录 inventory/checksum 尚未完成。 | E6 一次性 Legacy migrator、稳定 UUID、`legacy_identity_map`、只读 Git/备份输入和 digest 对账。 | 目标和约束已纳入；inventory/迁移未执行。 |
| C12 | 授权与审计合同分散，缺角色分离、approve/revoke 和传播测试。 | AR-2/S2 授权审计合同、E3 角色分离、撤销传播、correlation ID 对账。 | fail-closed 合同已纳入；闭环实现和负向测试待 AR-2。 |
| C13 | 前端验证基线有时效性，不能把旧复跑当当前状态。 | 阶段记录要求记录实际日期、工作树、版本和限制；未复跑项保持未验证。 | 规则已纳入；新的真实前端/E2E 基线待对应阶段。 |
| C14 | 横切运营能力缺 owner、阈值和退出证据。 | 模板的 owner/approver/阈值/回滚字段；运营项挂入 AR-2/AR-3/AR-4/AR-6 退出条件。 | 记录格式已纳入；具体 owner 和演练待各阶段建立。 |

## 4. 当前仍不能宣称完成

- `AR-0 + SK-0` 仍未通过；没有获批的真实等价 MySQL/Chroma 单机拓扑、故障注入、RPO/RTO 和 restore-forward 证据。
- 统一角色分离、`grant approve/revoke`、撤销传播和完整授权审计仍未实现。
- AR-1 至 AR-6 的 schema、认证切换、SQL runner、业务迁移、RAG/Skill 收敛、过渡依赖删除和单机恢复验收均未完成。
- 本清单本身不改变冻结范围，不触发数据库连接、迁移、删除、部署切换或新功能发布。

## 5. 参考优先级

1. 当前执行以[架构重写计划](../../architecture_rewrite_plan.md)为准。
2. 目标边界和 q85-q92 记录以[最终重构蓝图](../../architecture-target-blueprint-2026-08-26.md)为准。
3. 执行顺序、证据、停线和回滚以[执行交接手册](../../architecture-execution-handoff-2026-08-26.md)为准。
4. 本清单和[改动路线审阅报告](./change-route-review-2026-08-26.md)仅用于理解审阅依据和追踪未收口项。
