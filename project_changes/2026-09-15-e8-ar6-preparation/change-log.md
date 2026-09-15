# E8 准备变更记录

| 时间 | 变更 | 结果 | 回滚/边界 |
|---|---|---|---|
| 2026-09-15 | 核验 E6/E7 最终关闭索引和 539/29 证据 | 通过 | 历史证据只读，未写目标 |
| 2026-09-15 | 发现目标容器和 Doki 进程曾退出；恢复指定目标容器到 healthy | 已恢复运行，未改数据 | 仅 `doki-e4-20260903-mysql`；未操作 new-api |
| 2026-09-15 | 创建 `e8_prepare.py`、E8 计划与处置清单 | 准备报告生成；删除全部关闭 | 新批次文件可审查，保留历史材料 |
| 2026-09-15 | 记录当前 new-api 状态 | 仅观察；当前状态与历史 E6/E7 快照分开记录 | 不修改配置、权限、进程 |
| 2026-09-15 | 完成 E8 依赖引用图、候选 runbook、健康/runner/回归复核 | 26 项回归通过；收口判定为阻塞 | Redis 正确性依赖及旧文件/RAG 引用仍待改造；未删除资源 |

## 当前未执行

表删除、文件删除、旧 Chroma 删除、Django/Redis 下线、FastAPI-only 部署切换、全局门禁解冻、产品工作包解冻、生产 RPO/RTO 验收均未执行。

## 当前判定

E8 尚未关闭。下一步必须先完成 Redis durable pending action、旧 RAG/MD5/Skill 文件路径退出或显式运维隔离，再在新副本完成三类 Smoke 和 RPO/RTO，最后提交逐项删除清单供用户单独批准。

- 2026-09-15: Added durable SQL pending actions with owner checked row-lock consumption, E8 schema revision, optional Redis readiness/degradation contract, and controlled target migration evidence.
| 2026-09-15 | E8 final gates and closure | Passed | Three fixture smoke, RAG branches, SQL/Chroma reconciliation, RPO/RTO, and legacy reference audit recorded; `new-api` unchanged and historical resources retained |
