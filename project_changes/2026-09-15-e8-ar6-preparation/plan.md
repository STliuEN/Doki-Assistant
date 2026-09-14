# E8 / AR-6 准备计划

- 日期：2026-09-15；状态：`实施中`（仅准备）
- 入口：E6/E7 已获用户批准收口；用户现批准 E8 准备。
- 负责人：Codex；架构和最终关闭决定：用户。
- 当前结果：E6/E7 关闭证据已核验，E8 预检与处置清单已建立。E8 的删除、下线、最终部署切换、RPO/RTO 正式验收和门禁解冻尚未执行。

## 目标

准备 AR-6/S7-S8 的单机部署、恢复、过渡依赖处置和最终验收。业务权威仍为 `127.0.0.1:33427/doki_e4`；所有数据库操作保持在本机指定 Doki 目标内。

本阶段建立可审查的依赖清单、备份摘要、恢复路径、冒烟矩阵、停写窗口和删除审批点。准备期间不删除文件、表、Chroma generation、容器、卷、网络或代码；不停止 Django、Redis、new-api 或现有业务服务；不改变 MySQL 全局只读设置。

## 范围

| 面 | 准备内容 | 当前状态 |
|---|---|---|
| S7 过渡依赖 | Django、Redis、旧 YAML/Registry/MD5/目录 adapter 的引用图和替代路径 | 待实施 isolated proof |
| S7 单机运行 | FastAPI-only install/start/stop/upgrade/rollback/recover runbook | 待创建和副本验证 |
| S8 恢复 | 空库、恢复库、当前迁移库三类 smoke；SQL→Chroma 重建；FK/digest/audit 对账 | E6/E7 副本证据可复用，E8 独立 runbook 待验证 |
| S8 指标 | 写暂停、RPO、RTO、恢复后 generation 和服务就绪 | 待测量 |
| 清理 | 物理旧输入、Django/Redis、旧 adapter、旧 generation 的 allowlist | 只盘点，全部 `delete_enabled=false` |

## 前置证据与目标

E6/E7 关闭依据为 [closure-review.md](../2026-09-14-e6-e7-ar5-joint/closure-review.md)、[closure-decision-20260915.json](../2026-09-14-e6-e7-ar5-joint/artifacts/closure-decision-20260915.json) 和 [closure-index-20260915.json](../2026-09-14-e6-e7-ar5-joint/artifacts/closure-index-20260915.json)。目标包、授权、媒体、HTTP/SSE、SQL-only 恢复和真实本机模型证据均已记录。E8 不重新解释 E6/E7 历史证据为删除授权。

本次预检报告：[e8-preparation-20260915.json](./artifacts/e8-preparation-20260915.json)。它记录目标容器、new-api 观察、服务端口、最终目标备份摘要和过渡目录数量；不包含密码、JWT、SQL 正文或私有 hash。

## 工作包

1. 生成引用图：标出 Django/Redis/旧文件、MD5、Chroma 和 Registry 的所有运行时读写路径，确认 FastAPI→SQL 是唯一业务写入口。
2. 为 FastAPI-only 形态补齐 install/start/stop/upgrade/rollback/recover runbook，在新隔离副本验证，不覆盖当前目标。
3. 使用新副本完成空库迁移、目标备份恢复和当前迁移库 smoke；核对用户/会话/Skill/RAG/聊天/笔记/导出、FK、digest、audit 和 generation。
4. 在隔离副本测量 RPO/RTO 和应用级写暂停；MySQL 只允许受控应用写路径暂停，不使用全局 `read_only`、全库锁或主机停机。
5. 把每个旧资源写入处置 allowlist，先 `retain`，完成对账和恢复验收后再由用户单独批准具体删除。

## 退出条件

- E8 代码和 runbook 在空库、恢复库、当前迁移库三类副本通过启动、登录、会话、Skill、RAG、聊天、笔记和导出 smoke。
- 旧资源引用图完整；每个删除项有备份、摘要、责任人、回滚路径和恢复后对账。
- RPO/RTO、停写窗口、恢复后 SQL/Chroma/audit 对账有真实记录。
- 当前目标和 new-api 的基线可解释，且 E8 运行未改变 new-api。
- 用户另行明确批准删除清单，并分别确认是否解冻 `SKILL-GATE`、`ARCH-GATE` 和产品工作包；准备完成本身不自动触发这些动作。

## 回滚与边界

所有 E8 实验在新容器、卷、网络和 Chroma 工作目录执行。失败时保留日志和快照，使用 restore-forward 恢复副本。当前目标备份、E6/E7 失败报告、旧输入、容器、卷、网络和私有凭据全部保留。`new-api` 为外部保留资源，只观测 ID、启动时间、restart_count 和状态。
