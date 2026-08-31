# E3/AR-2/S2 变更日志

状态：待你确认  
负责人：Codex  
执行口令：`开始执行e3`

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-08-31 | `project_changes/2026-08-31-e3-ar2-fastapi-auth/plan.md` | 新建 E3 完整开发计划，记录身份迁移、cookie/token、session、角色、grant、审计、shadow、切换、回滚和退出条件 | 将 E3/AR-2 的共享理解固化为唯一执行入口 | 仅新增计划文档；未改代码、schema、配置、前端、数据库或外部资源 | 删除本批文档；不影响运行状态 | Codex | `E3-PREP-01` |
| 2026-08-31 | `project_changes/2026-08-31-e3-ar2-fastapi-auth/change-log.md` | 新建变更记录模板并登记当前仅文档准备状态 | 遵循阶段三件套和两次大确认纪律 | 仅新增文档 | 删除本批文档 | Codex | `E3-PREP-01` |
| 2026-08-31 | `project_changes/2026-08-31-e3-ar2-fastapi-auth/test-record.md` | 新建测试/迁移证据占位，明确所有实施项在执行口令前为 `not-run` | 防止把静态审阅误写成认证或迁移证据 | 仅新增文档 | 删除本批文档 | Codex | `E3-PREP-01` |
| 2026-08-31 | `project_changes/README.md` | 增加 E3 计划入口 | 使当前阶段材料可追溯，避免与 E2 记录混淆 | 仅更新历史变更索引 | 恢复 E3 入口行 | Codex | `E3-PREP-02` |

## 明确未做

- 未收到新的 `开始执行e3` 执行确认，因此没有实现任何 `E3-*` 任务。
- 未修改 backend/frontend/Alembic/OpenAPI/配置或测试代码。
- 未连接或修改 Django、MySQL、Redis、Storage、Chroma 或任何 Docker 资源。
- 未读取项目 `.env`，未导入用户/hash/session/token，未执行 migration、shadow、proxy 切换或认证切换。
- 未执行 Git 提交、推送、资源删除或历史数据清理。

## 后续记录规则

每个实现变更必须关联一个 `E3-*` 任务、一个回滚点和一个证据 ID；实现完成只能记录为 `待验证`。用户完成第二次验收确认后，才可将本批状态改为 `已关闭`。
