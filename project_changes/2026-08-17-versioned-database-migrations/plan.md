# 工作包 5：版本化数据库迁移

日期：2026-08-17
状态：已完成（最终复核：2026-08-18）
关联记录：同目录 `change-log.md`、`test-record.md`

## 目标

将 Django 与 FastAPI 的数据库结构管理从应用启动流程中移出，改为可审计、可重复执行的显式迁移流程。现有用户数据库只允许在完成备份和结构核验后由运维人员主动迁移，本工作包不会连接或修改任何现有数据库。

## 实施范围

- 提交 Django `user` 应用的初始 migration，并取消 `AppConfig.ready()` 中的建库、`makemigrations`、`migrate` 和固定管理员创建逻辑。
- 为 FastAPI/SQLAlchemy 引入 Alembic，提交覆盖当前模型的 baseline migration，并包含 ORM 要求的唯一约束。
- 删除 FastAPI startup 中的 `create_all` 和自定义缺列 `ALTER TABLE` 行为。
- 在 CI 使用临时 SQLite 空库验证 Django migration，并用 Alembic head、metadata 合同和 offline SQL 验证 FastAPI baseline；同时检查模型是否存在未生成的 Django migration。
- 更新开发、故障排查和版本路线文档，明确空库初始化、现有库接管、升级与回滚边界。

## 数据安全边界

- 不连接、不读取、不写入当前 `.env` 指向的 MySQL 数据库。
- 自动验证仅使用临时 SQLite 数据库或 Alembic offline SQL。
- 现有 FastAPI 数据库必须先备份并核对表结构，再执行 `alembic stamp 20260817_0001` 接管；不得直接对未知结构执行 baseline。
- schema downgrade 会删除业务表，只用于一次性空库验证，不作为生产回滚方案。生产回滚必须恢复备份或执行经过评审的前向修复 migration。

## 回滚方式

代码回滚可恢复旧启动逻辑和移除 migration 文件，但这不会自动回滚任何已执行的数据库变更。若 migration 已在环境中执行，应先停止服务，按环境的备份/恢复方案回退数据库，再回滚应用版本。
