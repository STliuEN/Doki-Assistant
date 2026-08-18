# 工作包 5 变更记录

日期：2026-08-17
状态：完成

## 已完成

- 调整 `.gitignore`，不再忽略 Django migration 源文件，仅忽略 migration 缓存和字节码。
- 提交 Django `user` 应用的 `0001_initial.py` 与 `0002_user_token_version.py`，使当前用户结构和认证版本字段可审计迁移。
- 删除 Django 应用加载期间的自动建库、`makemigrations`、`migrate` 和固定账号创建副作用；数据库变更改由显式命令执行。
- 新增 `backend/alembic.ini`、Alembic 环境和 `20260817_0001_baseline.py`，baseline 覆盖当前 FastAPI/SQLAlchemy 模型及 `uq_knowledge_source_user_md5`、`uq_user_embedding_config_user_id` 唯一约束，revision 为 `20260817_0001`。
- 删除 FastAPI 启动期间的 `create_all` 和自定义缺列补丁；lifespan 启动时只读取 `alembic_version` 并校验必须 revision，不自动修改 schema。
- 新增 migration 合同测试，防止 `create_all` 回到启动路径，保证应用要求的 revision 与 baseline 一致，并把 baseline 唯一约束集合与 ORM metadata 动态对比。
- Alembic 依赖加入 backend 锁文件，并重新生成 backend 与 Django 的 `requirements.txt` 导出产物。
- CI 增加 Alembic head/offline SQL、Django migration drift、system check 和 Django tests 门禁。
- 同步开发、部署和故障排查文档，区分空库初始化、已知现有库接管、升级与恢复边界。
- 2026-08-18 最终审计发现并补齐 baseline 中两个 ORM 唯一约束；离线 SQL 已确认新空库会创建对应约束，未对现有数据库执行任何操作。

## 兼容性与数据边界

- 空 FastAPI 数据库使用 `alembic upgrade head` 初始化；空 Django 数据库使用 `python manage.py migrate` 初始化。
- 未带 `alembic_version` 或 revision 不一致的 FastAPI 数据库会阻止应用启动，不会被启动代码静默修改。
- 现有 FastAPI 数据库必须先备份、核对 baseline 表结构，再由运维人员显式执行 `alembic stamp 20260817_0001` 接管；未知结构不得直接 stamp。
- 本工作包的自动验证只使用临时 SQLite 或 Alembic offline SQL，未连接、读取或修改现有 MySQL。
