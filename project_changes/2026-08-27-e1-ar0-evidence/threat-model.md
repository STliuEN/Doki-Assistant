# E1 威胁模型与保护边界

状态：已关闭

本文件只描述 E1（AR-0/SK-0）的单机、隔离依赖和保护性切片。它不是 AR-2 授权审计或 AR-6 生产安全评估的替代物。

## 范围与信任边界

```text
局域网浏览器
  -> Vite/React 开发前端
  -> Django 用户适配（过渡）与 FastAPI 业务 API/SSE
       -> 隔离 MySQL（E1 合成业务事实）
       -> Chroma（可重建 RAG projection）
       -> 本地模型/Embedding/Reranker（本批不验证质量）
       -> 显式备份/恢复工具与 E1 证据目录
```

E1 中浏览器、应用进程、Docker 容器、备份目录和现有业务环境属于不同边界。隔离依赖演练只使用 `doki-e1-20260827-*` 容器、loopback 端口和 `project_changes/2026-08-27-e1-ar0-evidence/` 下的合成数据。一次无效 pytest 读取 `.env` 后连接了本机 MySQL/Redis，CORS 失败复现和一次 benchmark 还触碰默认 Skill Storage；这些事故不作为 E1 证据，且无法绝对证明数据库/Redis 零写入。最终接受的 pytest/benchmark 已强制隔离，详情见 `test-record.md`。

## 资产

| 资产 | 机密性/完整性目标 | E1 保护方式 | 证据 |
|---|---|---|---|
| MySQL 用户、会话、Skill、聊天和审计事实 | 不越权读取；恢复后行数和 digest 一致 | 隔离容器、loopback、dump manifest、恢复/restore-forward 对账 | `artifacts/logs/mysql-recovery-summary.json` |
| Chroma chunks、metadata、vectors | projection 可重建；失败不得覆盖健康目录 | 只读 preflight、collection/迁移校验、quarantine、结构化 `503` | `artifacts/logs/chroma-rebuild-attempt2.json`、`tests/test_chroma_containment.py` |
| Storage/Chroma backup bundle | 篡改或路径穿越不得进入恢复目标 | 每个 payload 文件 SHA-256、路径/symlink/目标冲突检查、fail-closed | `artifacts/tamper-rejection/`、`tests/test_backup_restore.py` |
| Prompt、Skill、Tool grant 与 run binding | 未授权 Skill/Tool 不得进入一次运行 | 显式 Skill 校验、工具解析、revision/digest binding、高风险确认 | `tests/test_skill_tool_authorization.py`、`tests/test_tool_guard.py` |
| 浏览器 token 与 API 错误 | 401 不循环重试；503 不被当成成功 | 单次 refresh、401 清理状态、统一 JSON envelope | `front/src/api/client.ts`、`tests/test_chroma_http_containment.py` |
| 现有用户数据和脏工作树 | 本批不可变 | 目标边界是不连接、不迁移、不删除；误连事故完整披露，最终门禁使用临时资源并核对受保护目录/日志不变 | `plan.md`、`test-record.md` |

## 威胁与控制

| ID | 威胁/故障 | E1 控制 | 实测结论 | 残余风险/后续 |
|---|---|---|---|---|
| T1 | Chroma SQLite 损坏导致启动或查询异常 | 初始化前只读检查；失败标记 `quarantined`，不清空原目录 | 损坏副本被隔离；原树 digest 保持不变；RAG 依赖返回 503 | 仍需在 AR-4 交付 SQL 重建和 generation 规则 |
| T2 | Chroma 权限错误 | 失败不写入 projection；恢复 ACL 后显式重试 | Windows ACL deny-read 触发 quarantine，恢复后 ready | 原生 Linux/macOS 权限语义未跑 |
| T3 | Chroma schema/迁移版本不兼容 | SQLite migrations 只读比对；禁止构造时隐式迁移 | hash mismatch 被拒绝并 quarantine | 未来升级需独立离线迁移和批准 |
| T4 | collection 缺失时客户端自动重建并污染目录 | 预检要求 `rag_collection` 与 `notes_collection`，已有目录禁止自动创建 | 缺失 collection 在 Chroma 打开前失败；目录未变化 | generation 表和异步重建属于 AR-4 |
| T5 | 进程重启或活动客户端指向错误目录 | rebuild 后要求进程重启；禁止 retarget active client | 新解释器重启后语义 digest 一致；活动客户端 retarget 被拒绝 | runner kill/restart、lease/fencing 属于 AR-1 |
| T6 | 备份 payload 被篡改 | manifest 和逐文件 digest 校验先于复制/交换 | Storage 与 Chroma 均 exit 1，错误为 `backup payload does not match manifest`，新目标不存在 | 生产密钥管理、离线介质和 PITR 不在 E1 |
| T7 | 路径穿越、绝对路径、symlink 或已存在目标 | 规范化相对路径、拒绝 symlink/特殊文件/目标冲突 | Windows/POSIX 路径 fixture 和 symlink 测试通过 | junction/hardlink 与原生平台组合仍需平台实测 |
| T8 | Chroma 故障被 API 当作成功或挂起流 | 异常统一映射 `503`；stream/config mutation 在开始前 preflight | 13 个 Chroma 相关 API route 的 envelope、OpenAPI 声明和 source list 例外通过 | 目标 schema startup/readiness 归 E2；真实 Chroma-backed API/UI 成功流归 E5 |
| T9 | Skill/Tool 越权、revision 漂移或确认重放 | Skill 选择先校验；run binding 保存 revision/digest；确认失效返回 410 | 离线授权/guard suite 通过；benchmark fixture 显式绑定最小授权 Skill，最终 smoke `4/4`、regression `117/117` | AR-2 才能完成角色分离、撤销传播和审计闭环；离线通过不证明真实模型质量 |
| T10 | Prompt injection 诱导暴露未授权能力 | Prompt 明确当前启用 Skill 和工具上界；未列出能力不可用 | 确定性 benchmark 覆盖文本边界和 forbidden tool 字段 | fixture 不证明真实 LLM 的抗注入质量 |
| T11 | 数据库 schema 不符合应用启动要求 | 启动只读检查 `DATABASE_SCHEMA_REVISION`，不自动 DDL；纯 CORS 合同不启动 lifespan | 历史 schema 阻断和误连结果保留；最终隔离 pytest `284 passed`，本批未执行 migration | 真实目标 schema startup/readiness 需 E2 单独批准；认证/业务/RAG UI E2E 分属 E3/E4/E5 |
| T12 | 前端代理/后端不可用导致误判 | 记录浏览器网络和可见错误；不把 502 当业务成功 | `/register` 代理到不存在后端得到 502，页面显示“注册失败，请重试” | 真实后端 UI E2E 仍未运行 |

## 不在 E1 证明范围

- 真实 LLM、Embedding、Reranker 的质量、吞吐、成本或外部 provider 可用性。
- 原生 Linux/macOS、HA、多实例、公网 TLS、高并发和跨机时钟一致性。
- AR-1 SQL schema/UoW/job/runner、AR-2 角色/撤销/审计闭环、AR-4 generation 生命周期。
- 生产 secret、备份介质保密性、PITR、RPO/RTO 数值和灾备演练。
- benchmark 通过不等于模型质量通过；`skill_tool_selection`/`tool_safety` fixture 已按最小授权 Skill 修复，但只证明离线合同。

## 接受规则

E1 的真实/替身边界、故障结果、事故限制和未运行项已完成审阅，用户于 2026-08-27 明确确认关闭。任何后续发现的 fail-open、健康 Chroma 被覆盖、manifest 篡改被恢复、未知 schema 自动迁移或未披露的业务数据副作用，都必须重新打开风险评估并停止对应路径。E1 关闭不授权实施 E2/AR-1。
