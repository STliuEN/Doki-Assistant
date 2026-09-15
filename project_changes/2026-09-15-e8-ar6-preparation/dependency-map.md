# E8 过渡依赖引用图

盘点日期：2026-09-15。本文是 E8 收口前的事实清单；出现“保留”表示尚未获准删除，不表示该依赖已经退出运行。

## 当前运行链

| 依赖 | 当前入口 | 当前用途 | E8 退出条件 | 状态 |
|---|---|---|---|---|
| DjangoUserService | `DjangoUserService/`、`scripts/start-all.ps1` | 历史用户服务、旧启动脚本、迁移输入 | FastAPI-only 空库/恢复库/当前库登录、资料、会话、撤销与回滚 Smoke 通过 | 运行目录保留；不能删除 |
| Redis | `backend/main.py`、`backend/app/db/redis_config.py` | 启动 ping、健康 ready、限流计数、缓存辅助、待确认动作 TTL/GETDEL | 正确性路径全部转 SQL；限流和短期缓存允许单独降级策略；Redis 断开时业务 Smoke 仍满足合同 | **阻塞**：待确认动作仍完全依赖 Redis，ready 仍要求 Redis |
| 旧 Chroma / MD5 | `backend/app/rag/vector_store.py`、`backend/app/rag/md5_manager/md5_store.py`、`backend/app/config/chroma.yaml` | 遗留知识写入、MD5 目录索引、旧向量服务兼容路径 | 正式 E5 SQL projection 路径覆盖所有业务读写；旧路径仅显式 import/export/debug，故障无 fallback | **阻塞**：旧路由和 `VectorStoreService` 仍可触及这些路径 |
| Skill objects | `backend/app/skills/storage.py`、`backend/data/skill_packages/objects/` | 旧包存储、seed/兼容路径 | 全部运行时读取来自 SQL package/resource repository，旧对象只作为可核验备份 | **阻塞**：`resource_tools.py` 和存储兼容代码仍保留文件实现 |
| 本地配置 | `backend/app/config/{chroma,mcp,security}.yaml`、`reranker_config.json` | 运行配置和外部 MCP 声明 | SQL/环境配置的权威边界、显式本地运维开关和恢复记录写清 | 部分已迁移；MCP 外部能力继续 disabled |
| `new-api` | Docker `new-api`、端口 11451 | 外部保留服务 | 不属于 E8 操作范围，只记录 ID/状态 | **排除**：不停止、不改配置、不改权限 |

## Redis 细分引用

1. `main.py:lifespan` 在数据库和 Skill registry 初始化后调用 `connect_redis()`，关闭时调用 `close_redis()`。
2. `health.py` 将 `check_redis_connection()` 纳入 `/health/ready` 的 `core_ready`。
3. `core/rate_limit.py` 使用 Redis Lua fixed-window 计数；多个 router 通过 `Depends(rate_limit(...))` 调用。
4. `services/pending_action_store.py` 使用 Redis `SET EX` 写入待确认动作，使用 Lua `GET`/`DEL` 做用户校验和一次性消费。
5. `cache/redis_decorator.py` 是通用缓存辅助，不能承担业务正确性。

E8 处理顺序：先为待确认动作建立 SQL durable record 和原子消费接口，再决定限流的 fail-closed/本地短窗策略；随后把 `/health/ready` 改成只检查 SQL 和明确列出的可选缓存状态。每一步先在新副本执行，禁止先停 Redis 验证当前目标。

## 文件与 Chroma 细分引用

- `knowledge_router.py`、`knowledge_service.py` 和 `vector_store.py` 仍导入遗留 `VectorStoreService`；旧服务内部构造 `MD5Store` 并读取 `chroma.yaml` 的目录。
- `knowledge_image_paths.py` 仍解析 `data/extracted_images`，但 E6/E7 SQL media 路径已覆盖生产图文读写；需要为旧路径增加显式运维开关和调用审计后才可处置目录。
- `skills/resource_tools.py` 从 `skill_package_storage` 读取资源；E6/E7 SQL resource 验收已存在，但正式路由还必须完成 SQL-only 强制切换并在缺 SQL 包时 fail-closed。
- `backend/data/chromadb`、`backend/data/md5_hex_store`、`backend/data/extracted_images`、`backend/data/skill_packages/objects` 均保留。任何物理删除前必须生成新备份、文件级 SHA、引用扫描和 restore-forward 记录。

## 删除顺序

1. 完成 SQL durable pending action、SQL-only Skill resource 和 SQL-only knowledge read/write。
2. 在新副本停止 Redis，执行登录、会话、Skill、RAG、聊天、笔记、导出和待确认动作 Smoke；记录哪些接口降级以及合同状态码。
3. 在新副本运行 FastAPI-only install/start/stop/upgrade/rollback/recover；Django 仅作为保留回滚材料。
4. 生成带逐项 `retain/migrated/delete-candidate` 状态的清单，复核备份和恢复路径。
5. 用户逐项批准后，才执行具体物理删除或服务下线。
