# 工作包 5 测试记录

日期：2026-08-17
状态：完成

## 迁移验证

```text
backend> uv run --frozen alembic heads
20260817_0001 (head)

backend> uv run --frozen alembic upgrade head --sql
passed

DjangoUserService> ENV=test + SQLite + LocMemCache
python manage.py check: passed
python manage.py makemigrations --check --dry-run: No changes detected
python manage.py test: 19 passed
```

Backend migration 合同测试包含在全量 `118 passed` 中，验证启动代码不调用 `create_all`、应用要求的数据库 revision 与提交的 Alembic baseline 一致，并动态比较 baseline 与 ORM metadata 的唯一约束名称。Alembic offline SQL 明确生成 `uq_knowledge_source_user_md5` 和 `uq_user_embedding_config_user_id`；临时 SQLite 浏览器环境也已成功执行 Django migrations 后完成注册、资料读取和注销。

首次执行 requirements 漂移检查时准确发现新增 Alembic 后的 `backend/requirements.txt` 尚未同步；重新生成 backend 与 Django requirements 后，两端 `uv lock --check` 和 `scripts/export-requirements.ps1 -Check` 均通过。

## 最终发布门禁

| 检查 | 结果 |
|------|------|
| Backend pytest / Ruff | `118 passed`；Ruff 通过 |
| Django | system check、migration drift、`19 passed` |
| Frontend | `20 passed`；lint、构建通过 |
| FastAPI OpenAPI | current |
| Lock / requirements | backend、Django lock 与导出产物检查通过 |
| Offline Benchmark | smoke `4/4`；regression `117/117`，hard veto `0` |

## 数据安全结论

所有 migration 检查只使用临时 SQLite、静态源文件检查或 Alembic offline SQL。没有连接、读取或修改 `.env` 指向的现有 MySQL；也没有对未知现有库执行 `stamp`、upgrade 或 downgrade。
