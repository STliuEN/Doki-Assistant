# E8 单机部署与恢复手册（收口候选版）

本文描述 E8 目标流程。当前仍是候选手册，直到三类副本 Smoke 和 RPO/RTO 记录完成，不得用于物理删除或生产切换。

## 运行前检查

1. 使用新目录保存 invocation、allowlist、preflight、日志和进程记录。
2. 核对 `doki-e4-20260903-mysql`、`127.0.0.1:33427/doki_e4`、SQL UUID、schema revision 和当前代码 SHA。
3. 生成 data-only 和完整 SQL 备份，保存 SHA、字节数、表计数、FK/orphan、RAG generation、audit 最大时间和 new-api 观察值。
4. 不连接主机 3306，不设置 `read_only`/`super_read_only`，不锁全库，不停止或修改 new-api。

## FastAPI-only 副本

在新 MySQL/Chroma/工作目录启动 FastAPI，使用 SQL authority 环境变量和显式 runner 配置。启动检查必须覆盖：schema、SQL package/resource、MySQL、所需缓存策略、RAG owner generation 和 runner。停止检查必须确认 SQL 事务完成、runner drain、Chroma snapshot 和日志落盘。

当前代码不能直接声称通过此步骤：启动仍强制连接 Redis，待确认动作仍写 Redis，旧 RAG 路径仍存在。必须先按 [dependency-map.md](./dependency-map.md) 完成对应改造。

## 三类恢复 Smoke

| 副本 | 操作 | 必测流程 | 通过条件 |
|---|---|---|---|
| 空库 | Alembic upgrade head，导入最小 SQL fixture | 启动、注册/登录、session、Skill catalog/授权、RAG owner 状态、聊天、笔记、导出 | 无隐式 Django/Redis/文件 fallback；审计和 schema 对账通过 |
| 恢复库 | 从最终目标备份 restore-forward | 同上，加包/资源/媒体/grant/revoked Run、Chroma 重建 | data-only SHA、表计数、FK、digest、generation、audit 对账通过 |
| 当前迁移库 | 新副本加载当前迁移快照 | 原用户登录、历史会话、Skill/资源、知识/图片、笔记、聊天和导出 | owner 隔离、稳定 UUID、授权状态、无孤儿；失败时可恢复 |

## 升级、回滚和恢复

- upgrade：新目录备份 -> schema dry-run -> 新副本升级 -> 迁移对账 -> API smoke -> 记录 revision。
- rollback：停止写入应用路径 -> 保存日志和快照 -> 恢复最近健康 SQL/Chroma -> 校验 digest/FK/audit -> 重新启动 FastAPI。
- recover：从 SQL 备份恢复业务权威，从 SQL 原文重建 Chroma；不恢复旧文件作为业务 fallback。
- stop：只使用记录目录中的 `stop_development.py`，核对 PID、命令、cwd 和子进程；不按端口或名称杀进程。

## RPO/RTO 记录

每次副本演练记录：最后成功事务时间、应用级写暂停开始/结束、备份开始/结束、MySQL restore 开始/结束、Chroma rebuild 开始/结束、API ready 时间、首个成功登录时间、恢复后对账时间。RPO 是最后成功事务到故障点的时间差；RTO 是故障点到 API 和数据对账均通过的时间。

## 删除审批点

下列项目默认 `delete_enabled=false`：Django runtime、Redis 容器/缓存、旧 YAML/Registry adapter、MD5 sidecar、`extracted_images`、旧 Chroma generation、旧 Skill objects、失败 fixture 和历史容器/卷/网络。每个项目需要独立备份、SHA、引用扫描、恢复路径和用户批准；任何一个未满足都保持 retain。
