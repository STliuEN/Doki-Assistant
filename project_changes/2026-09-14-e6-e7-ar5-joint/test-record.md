# E6/E7 联合测试记录

最后更新：2026-09-15；阶段 `已关闭`。最终后端 539、前端 29、lint/build 及 JV01–JV09 通过；见 [收口判定](./closure-review.md) 和 [最终证据](./artifacts/closure-decision-20260915.json)。以下准备与早期执行记录是历史快照。

| ID | 动作 / 环境 | 结果 | 证据边界 |
|---|---|---|---|
| JP01 | 校验 E5 evidence-index 的 67 个工作树文件＋45 个 artifacts | 112 项摘要通过并封存 ZIP，含原索引 | 后续主文档变更不回写原 E5 封存基线；不是新数据库备份 |
| JP02 | 精确 E5 target 专用账号 SELECT/SHOW；SQL 前后盘点 | 10 Skills、10 versions、10 enabled installs；SQL packages/uploads/media 0；6 原文/7 笔记/27 sessions/150 messages；前后一致 | 不迁移、不改全局只读、不消费 job |
| JP03 | objects/seed/images/MD5 输入扫描和 parser 校验 | objects 10/10 digest 通过；images 0、sidecar 1；文件清单和摘要前后相同 | 只读、拒绝 link/junction；不证明旧 raw upload 可找回 |
| JP04 | 10 个相关 pytest 文件；Windows venv，ENV=test、E5_RAG_ENABLED=true | **105 passed in 20.23s** | 既有 Skill/确认/Agent/图片路径回归；SQLite/临时文件等测试依赖，不代替真实新 schema/授权/媒体链 |
| JP05 | docs、prepare.py Ruff、git diff 检查 | 见 [checks.json](./artifacts/checks.json) | 本批文档/工具质量门禁 |

准备脚本及复现命令见 [ops README](../../backend/ops/e6_e7/README.md)。机器盘点见 [preparation.json](./artifacts/preparation.json)，后端摘要见 [baseline-tests.json](./artifacts/baseline-tests.json)。原 JUnit 与可能包含文件定位信息的明细只在 `.runtime/e6-e7-preparation-20260914`。

相关测试文件：test_skill_package、test_skill_storage、test_skill_service_transactions、test_skill_tool_authorization、test_skill_router_containment、test_no_legacy_skill_runtime、test_seed_manifest、test_confirmation_service、test_agent_run_service、test_knowledge_image_paths。

正式 JV 测试已按 contracts.md 补齐新恢复副本、真实 MySQL 授权/媒体、浏览器、重启/撤销和 SQL-only 恢复。新管理员身份由用户明确指定；不同账号角色分离已验证。物理旧数据删除、E8 部署及全局门禁未启动。

## 2026-09-14 早期执行记录（已由新证据更正）

| Date | Action / environment | Result | Boundary |
|---|---|---|---|
| 2026-09-14 | Fresh replica restore, 0010 upgrade, 10 Skill packages and 10 original uploads | Passed; installations changed to disabled | Separate replica container/volume/port; does not grant target authorization |
| 2026-09-14 | Replica SQL media positive/negative cases | Passed: owner read, cross-user rejection, corrupted bytes rejection | Synthetic image and replica fixture only; target historical media is zero |
| 2026-09-14 | Replica four-eyes authorization | Passed: self-approval rejection, independent approval, revoke/expiry/drift fail-closed | Temporary security_admin was replica-only and not written to target |
| 2026-09-14 | Target SQL/API checks | Passed: revision 0010, packages/uploads 10/10, 0 enabled/10 disabled, read_only 0/0; login/catalog/authorization 200; missing image 404 | Target has no security_admin or approved grant |
| 2026-09-14 | Quality gates | Backend 536 passed, 1 warning; frontend 29 passed, lint/build passed; Ruff/compileall/diff passed | One aiosqlite deprecation warning |

历史证据：[e6-e7-final-decision.json](./artifacts/e6-e7-final-decision.json)。旧媒体/授权脚本的断言局限见 closure-review.md；不能单独支撑最终通过。

## 2026-09-15 最终复核

新增首轮 Agent 会话 SQL 原子性与跨用户拒绝回归、SQL 健康检查禁用磁盘依赖回归；全量 `539 passed`。真实隔离验收通过：包/授权/媒体 10 组，HTTP/SSE/SQL断路重启 7 组，SQL-only 恢复及新 Chroma 6 个 owner/index 分片逐条校验。目标 10 包/10 uploads/0 imports，8 enabled/2 unsupported；新管理员 API 和浏览器登录通过。

最终 JUnit、Ruff/compileall/diff、前端 lint/build 和证据摘要由 `archive_closure.py` 汇总；运行目录中的私有凭据不进入公开 artifacts。

