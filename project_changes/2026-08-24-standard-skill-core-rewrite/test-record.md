# 标准 Skill 核心重构验证记录

日期：2026-08-24

状态：最终开发回归通过；`SKILL-GATE` 与 `ARCH-GATE` 未通过

## 最终自动化结果

| 检查 | 结果 |
|------|------|
| Backend pytest | `216 passed` |
| Backend Ruff | 通过 |
| Python compileall | 通过 |
| Backend lock | `uv lock --check` 通过 |
| Requirements drift | 通过 |
| FastAPI OpenAPI | current，生成物检查通过 |
| Alembic | 单一 head `20260824_0002`；upgrade/downgrade offline SQL 通过 |
| Django tests | `19 passed` |
| Frontend Vitest | `6 files / 28 tests passed` |
| Frontend lint/build | 通过 |
| Offline smoke | `4/4` |
| Offline regression | `117/117`，hard veto `0` |
| Markdown/本地链接 | `143 files / 132 local links`，通过 |
| Diff whitespace | `git diff --check` 通过 |

主要复核入口：

```powershell
cd backend
uv run pytest -q
uv run ruff check main.py app tests scripts
uv run python scripts/export_openapi.py --check
uv lock --check

cd ..\front
npm test -- --run
npm run lint
npm run build

cd ..
powershell -ExecutionPolicy Bypass -File scripts/check-docs.ps1
git diff --check
```

Alembic head、upgrade/downgrade offline SQL、compileall、requirements、Django 和 Benchmark 使用仓库对应的维护/测试命令独立复核，结果均通过。

## 已覆盖行为

- 标准 frontmatter/package/resource 解析，以及路径、链接、名称碰撞、体积和 ZIP 炸弹拒绝策略。
- 内容寻址 Storage、checksum、原子 finalize、重复 digest 和 package 不可变性。
- Skill 领域模型、Alembic contract、标准 seed、CapabilityGrant、SkillRunBinding 和 import `target_revision`。
- 管理员纯 draft catalog、普通 catalog/Registry 隐藏、private Skill/Tool 和显式 ID 授权过滤。
- publish/activate/rollback 的事务一致性与同 Session relationship 刷新。
- Registry revision/outbox reconcile、旧事件恢复、目标 revision 收敛和统一 stale `503`。
- A 级 Prompt、B 级版本绑定资源、统一 Tool 调用预算和高风险确认的运行快照固定。
- 前端资源上传、替换、删除、撤销、增量 `resource_changes` 和未修改资源保留。
- 前端允许 `format_compatible=true`、`runtime_ready=false` 的 C 包以 `enabled=false`、`default=false` 禁用安装，并保持不可启用、不可执行。
- 删除 20 个旧运行文件，并以静态测试禁止 `skill.yaml` loader、旧目录写入和双 Registry 回归。
- OpenAPI 生成物与已实现 Skill lifecycle 子集保持一致；import/export/error 合同仍有已知缺口，不能据此宣称当前完整 lifecycle 或错误合同已通过。

## 文档与 Git 产物检查

`scripts/check-docs.ps1` 会过滤 Git 索引中存在但当前工作树已经删除的 cached 路径，因此 `143 files / 132 local links` 只反映当前有效文档。旧 `backend/app/agent/skills` 文件以删除状态退出；标准 seed package 位于 `backend/app/skills/seed_packages`。

Benchmark results、前端 `dist`、临时 package/Storage staging 和其他中间产物均受 ignore 规则保护，没有进入 Git 跟踪清单。文档和运行验证未恢复已删除旧文件，也未新增独立的临时变更记录目录。

## 尚未执行的发布门禁

- 真实 MySQL migration/startup/完整 API lifecycle E2E。
- 任意第三方 A/B package 从导入到真实聊天资源读取的 API/浏览器 E2E。
- durable import worker 的 lease、幂等、重试、取消、背压、DLQ 和重启恢复。
- per-user scope 的真实数据库授权矩阵。
- 跨多次 B 资源读取的累计 token 预算。
- Node/npm 或 Python C 级 Skill 的构建、授权、独立 runner/沙箱、超时、取消、进程树终止和回滚 E2E。
- Storage 损坏、跨实例故障、恢复、跨平台和 clean install 的完整发布演练。

因此当前验证只证明 A 级和有限 B 级开发链路及其安全/一致性控制通过回归，不构成 `SKILL-GATE`、`ARCH-GATE` 或“通用可执行 Skill 已支持”的证据。

## 数据安全

验证使用离线、临时或静态检查，没有连接或修改现有 MySQL、Redis、Chroma 或用户文件，也没有对现有数据库执行 migration。
