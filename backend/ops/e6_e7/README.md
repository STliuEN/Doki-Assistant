# E6/E7 执行与验收入口

2026-09-15：E6/E7 在本机 SQL 权威、A/有限 B Skill 范围联合关闭。最终结果、真实依赖与自动回归的边界见[收口判定](../../../project_changes/2026-09-14-e6-e7-ar5-joint/closure-review.md)；[联合计划](../../../project_changes/2026-09-14-e6-e7-ar5-joint/plan.md)保留执行历史。

## 当前运行与工具

开发入口为 `http://127.0.0.1:18080`，启动记录在 `.runtime/e6e7-dev-ready-20260915/processes.json`。后端 18000，专用 Redis 18020/DB3，SQL runner 并发 1。`STliuEN` 为 skill_admin，新增 `STliuEN-security-admin` 为 security_admin；私有凭据仅位于 `.runtime/e6e7-target-closure-20260914/security-admin.private.json`。两个账号由同一用户授权操作，不代表两名自然人独立复核。

10 个历史包已迁入 SQL，稳定 ID/digest 保留；8 个本地 Skill 已授权启用，2 个外部 MCP Skill 保持 unsupported/disabled。授权约 30 天到期，延期走重新申请和审批流程。

| 工具 | 用途及修改边界 |
|---|---|
| `target_env.py` / `migrate_legacy.py` | 精确目标防护与已执行迁移；再次执行前核对脚本参数、备份和运行状态 |
| `target_closure.py` | 用户授权的账号、grant 与启用操作；曾部分提交，保留日志。不是通用无副作用重跑命令 |
| `target_audit.py` | 只读核对当前目标包、角色、授权、原文数量、RAG 状态和 new-api 基线 |
| `acceptance_env.py` | 备份受控源并恢复到本次新建的隔离副本；可验证空库升级，固定回环端口供重启测试 |
| `closure_acceptance.py` | 隔离副本真实包、授权、RunBinding、工具、任务、确认与图文验收 |
| `closure_runtime.py` / `restore_verify.py` | SQL runner 重建全新 Chroma；核对包/媒体/撤销/审计及逐条向量，验证缺失 Chroma 拒绝 |
| `http_closure.py` | 真实路由、SQL、本机 Ollama 的 HTTP/SSE 验收；仅停止/重启脚本允许的隔离副本 |
| `browser_login.py` | 既有 Playwright CLI 会话的实际登录；输出只保留结果，不保留带密码的 CLI 回显 |
| `start_development.py` / `stop_development.py` | 启动 Doki 开发服务、按记录核实并停止本次进程树；`--enable-runner` 显式开启 runner |
| `archive_closure.py` | 核验指定成功报告、JUnit 与当前服务，执行质量检查，归档非私有证据并封存 SHA；`--verify` 仅核对封存 |

下列只读审计和证据复核可用于当前批次：

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/target_audit.py .runtime/e6e7-target-closure-20260914
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/archive_closure.py --verify
```

重新验收须使用新目录，不能覆盖失败或历史 evidence。`acceptance_env.py <新目录> --source-directory <已校验副本目录> --empty-schema` 会创建新副本；不传 source-directory 时从固定业务目标备份。旧动态映射端口副本经历重启后可能与 allowlist 不符，不得修改旧 allowlist 绕过防护。

## 历史准备入口

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/prepare.py --directory .runtime/e6-e7-preparation-NEW --output project_changes/2026-09-14-e6-e7-ar5-joint/artifacts/preparation-NEW.json --baseline-archive .runtime/e6-e7-preparation-20260914/e5-sealed-inputs.zip
```

首次盘点不传 baseline-archive 时验证 E5 封存索引对应工作树；进入后续阶段后显式传入上述 baseline ZIP，逐文件验证其内部 SHA 及原 E5 index 绑定。这样验证的是历史已验收基线，不追认当前代码。原 ZIP 摘要在本批 preparation.json，新目录/输出必须独立，不能覆盖旧 evidence。

脚本复用 E5 已审查的精确目标只读身份定位，不调用 E5 consumer/preflight/迁移。SQLAlchemy 自己的连接仅允许 SELECT/SHOW；不设置服务器 read_only。仅连接固定 `127.0.0.1:33427/doki_e4`、专用账号与预期 container ID/UUID；不使用 host 3306。读取凭据仅为连接，不输出密码。扫描根限于 backend/data/skill_packages/objects、extracted_images、md5_hex_store 和仓库 seed_packages；不跟随 symlink/junction、不修改文件、不执行包代码或模型。

输出两层：公开 counts、digest、版本 ID、无变化观察；私有 per-file/source 清单和 E5 sealed baseline ZIP 存 `.runtime`。new-api 仅观测 ID/StartedAt/restart/status，不启动、停止或改变其配置。

准备不要求停服务。联合写操作已按 E6E7 stage/purpose allowlist、即时 preflight、二进制备份和新恢复副本执行；不能把 prepare.py 的成功作为写许可证。副本恢复先于原目标迁移；角色 bootstrap 已获得用户指定新建管理员的授权，并经不同账号申请/审批验证。

## 最终证据

最终后端 539、前端 29、lint/build 和 [JV01–JV09](../../../project_changes/2026-09-14-e6-e7-ar5-joint/contracts.md) 通过。真实 HTTP/SSE 使用应用原路由和本机模型；完整服务就绪及管理员浏览器另有证据。故障时 SQL 图片接口返回结构化 500 且无数据，不宣称 503；全局健康的 Chroma `owner_scoped` 也不代表所有用户均 ready。

`.runtime/e6e7-sql-only-restore-20260914` 保存带夹具的空库恢复和新 Chroma；`.runtime/e6e7-http-final-20260915` 保存故障/重启结果；`.runtime/e6e7-final-target-backup-20260915` 保存最终业务目标备份和新副本恢复。原始 SQL 与凭据不复制到公开 artifacts，索引只记录备份路径和摘要。

E5 封存索引、准备索引和旧 `e6-e7-final-decision.json` 保留为历史快照。当前结论以 `closure-decision-20260915.json` 与 `closure-index-20260915.json` 为准。旧文件/备份/容器/卷/网络继续保留；E8、C/scripts/外部 MCP、SKILL-GATE、ARCH-GATE 和产品工作包 7–10 均未启动或解冻。
