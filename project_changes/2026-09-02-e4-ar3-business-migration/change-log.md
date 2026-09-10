# E4/AR-3/S3 变更日志

## 2026-09-10 E4 closure decision (current)

- 用户明确批准关闭 E4，范围仅为状态关闭，不清理中间材料；所有历史 checkpoint、失败现场、备份和 restore-forward 证据保留。
- 关闭前的实施与验证证据已完成：迁移批次 `reconciled`、312 entities、源冻结/恢复、唯一写权威、旧入口封闭、生命周期/Redis/runner 矩阵、本地 Ollama 矩阵、浏览器预检和 SQL 审计核验。
- E4 状态：已关闭。E5/E6/E7/E8 仍须各自授权，不因本次关闭自动启动。

## 2026-09-08 本轮执行结论（历史记录）

- 本轮用户明确要求执行完整生命周期、Redis 故障、源停写、旧进程部署和 DSN/流量切换。已完成的是**本机单实例、loopback HTTP 的实际切换**，不是外网 DNS/LB/TLS 或多实例生产部署。
- 源库已于 `2026-09-08T00:50:34Z` 冻结并设置持久 `read_only/super_read_only`；`st@%` 已锁定/撤权。最终 21 表摘要未变，只读客户端零行 UPDATE 返回 1290。管理员仍能显式解除只读，不能宣称无法绕过。
- 三层服务实际运行于 Vite `18080`、FastAPI `18000`、retired Django `18001`。FastAPI 进程内观测确认 `doki_e4_app@%`、`doki_e4`、target UUID `0c0d3e33-a743-11f1-af41-ea47e0ceb469`；前端实际登录、cookie 刷新/注销、笔记写入和 `/jobs` 查询已穿过代理落到 target。
- 两次完整优雅 shutdown 释放 Redis pool 和 MySQL runner lock，重启重新获取锁。Redis 停止时 live/runner 为 200、ready 和依赖限流的业务请求为 503；业务/job/audit 摘要不变，恢复后无需重启应用即可写入。Redis 不可用时冷启动和 SQL runner 处理持久任务也通过。
- Django 实际进程 26 个 GET/POST 探针全部 410；ORM 写、迁移与直接 SQL 零行写入被拒绝。未启动未知旧二进制；在本机原本没有旧应用进程的前提下部署了当前 retired Django。
- 修复全生命周期暴露的 Skill registry bulk UPDATE，改为受追踪行变更并审计；补 Redis 限流 503/健康探针边界和前端 `/jobs` 代理。后端 491 测试、前端 28 测试、前端 build、Ruff、compileall 均通过。
- 最终独立恢复为 **39 表 / 2,539 行**（新增认证、审计、任务证据保留）；SHA-256 `bbcf14de7d4024aadc523d5e923fd73de917ad25c5396cf77c31b6c0d66a1b75`。原 312 业务实体、314 mappings、48 FK 复验通过；测试笔记经审计清理。
- 主证据：`artifacts/e4-full-lifecycle-cutover-20260908.json`；矩阵：`artifacts/e4-cutover-redis-20260908T024931.json`；源冻结：`artifacts/e4-source-freeze-20260908.json`；恢复：`artifacts/e4-restore-20260908T025045.json`。
- 限制：最终 FastAPI 是 `ENV=development` 的本地单实例，显式关闭 DEBUG 并启用限流；没有把本地目录冒称生产共享卷。曾设置 `SKILL_STORAGE_SHARED=true` 的早期尝试不构成共享存储验收，现运行配置为 false。Ollama 不可用降级已观察，未完成真实外部 LLM 成功/故障矩阵；E5/E6 未激活，迁移批仍为 imported，用户验收未发生。
- 安全跟进：早期诊断误输出过凭据，已轮换 target app 密码、approval、JWT signing secret 并验证旧密码失效，重建仅限 E4 target 且保留 volume/UUID；第三方 API key 仍需用户在供应商侧轮换。秘密及原始日志只存私有目录，不复制到公开证据。

日期：2026-09-02  
最近更新：2026-09-08（完整生命周期、Redis 故障及本机部署切流）
状态：已关闭
负责人：Codex  
审阅/批准人：用户  
用户确认：2026-09-02 完成 E4 执行授权；2026-09-10 明确批准关闭 E4，仅关闭状态，不清理中间材料。

## 2026-09-07 日常写权威实施与验证

- 收尾同步 rollback/source/write-path inventory 与 E4 ops README：以 39 表/2,407 行恢复及 PDF 审计排除为当前状态，区分代码防护、隔离验证与未执行的部署切流；修正 job 必须在业务事务内 enqueue。文档/差异/私有 ACL 与新增凭据精确扫描通过。

- 用户授权排除缺失测试 PDF；新增可追溯 SQL 排除审计，不删其它源。E4-06 新增 BusinessSession，统一 canonical owner/parent/digest 和业务 audit/job 同事务，拒绝批量旁路；MySQL 精度规范化避免 live digest 漂移。
- 日常笔记标签改持久 SQL handler；业务结果与 fenced job success 同 UoW，runner 核实已完成状态。聊天 parent+消息同 UoW，任务只消费已注册类型；inactive E5 projection 不假成功。
- 知识单/批/流式上传写 SQL 原件与 jobs；embedding 只保存配置并排队；增加 owner-scoped job list/detail。请求函数退出提交后才返回成功/accepted SSE。
- E4 禁用旧文件/MD5/reranker/tool/MCP HTTP 维护入口、旧 key-rotation apply；Django HTTP/ORM 写入口 fail-closed。未自动重启旧运行进程或改永久 DSN。
- 真实 smoke 与复验：`artifacts/e4-write-authority-20260907.json`；488 测试通过，Django 14 路径拒绝；39 表/2,407 行恢复全等，旧源21表和原312业务实体不变。
- 回滚：撤销本轮 runtime 接线/新模块可回旧代码；数据库不 downgrade，保留新审计/jobs/备份。旧源不写，E1-E3不动。完整 E4 仍实施中，待停写/切换/全生命周期和验收。

## 2026-09-07 测试用户重建与真实执行

- 用户明确数据库用户均为测试数据、允许推倒重做。本轮只重建隔离 E4 目标的 2 个 canonical 用户和本地随机登录凭据；源用户/业务行、旧输入与 E1-E3 资源保留。
- `E4-01/03/04`：创建 source 专用只读账号，轮换独立 target/restore app/root 凭据，锁定 restore 旧 app 账号；重建 E4 容器但保留 volume/server UUID；提交无秘密 allowlist，签发并消费真实 preflight，Alembic head 已部署 39 表。
- `E4-02/04/05`：补齐 62 条 Skill 必要输入 adapter、ISO datetime 转换，4 个密文配置实际解密并绑定版本；导入 312 条业务、314 mappings、0 quarantine；重放 0 imported/312 skipped，48 FK 无孤儿，6 原件 455,311 bytes 和 10 Skill 包对账。
- `E4-06`：真实认证暴露 canonical 登录后 legacy owner 查询不可见/错配；统一 owner predicate，非空 canonical 优先，阻止旧 ID 绕过。新增 2 个回归，覆盖 7 类业务 service；保留首次失败与修复后 API 证据。
- `E4-07`：真实 MySQL runner kill/restart、自然 lease 过期回收、MySQL 进程锁排他、幂等/冲突与旧 fencing 拒绝通过；不连接 Redis/Chroma，仅 synthetic handler，不等价完整业务端到端。
- 最终恢复：`2026-09-07T02:14:01Z` target/restore 39 表/2,245 行 DDL 和行摘要一致；旧备份保留。完整本地测试 `473 passed, 1 warning`，Ruff/compileall 通过。
- 证据索引：`artifacts/e4-live-execution-20260907.json`。回滚参见更新后的 runbook；不执行 populated downgrade，不用旧共享凭据回切。应用未停写或切 DSN；缺失 PDF、完整写权威/端到端和验收仍未完成。

## 2026-09-07 较早收口（历史；被本轮 live checkpoint 更新）

- `E4-01` / `E4-02`：补记真实只读快照、314 条身份 dry-run、MD5/文件/Chroma inventory 和现有 E4 容器启动后的身份/空库观察；证据为 `artifacts/e4-source-audit-20260906.json`、`artifacts/e4-source-identity-20260906.json`、`artifacts/e4-local-inventory-20260907.json`、`artifacts/e4-resource-discovery-20260907.json`。源/目标均未执行业务写入。
- `E4-03` / `E4-04`：增加 `backend/scripts/e4_preflight.py` 及失败前置/脱敏测试，修复 `backend/alembic/env.py` 和 `backend/app/db/db_config.py` 的容器 inspector 注入；证据 `E4-04-PREFLIGHT-CLI-20260906` / `E4-04-GUARD-WIRING-20260907`；基线全量 `447 passed, 1 warning`。
- `E4-04`：新增 `backend/app/e4/payload.py`，CLI 在 dry-run 和开启目标连接前校验业务 adapter、行形状/必填列、配置 key-version、文档和媒体字节；只输出问题代码/source-key 摘要，已知失败不进入 live guard。证据 `E4-04-PAYLOAD-20260907`；CLI 定向 `24 passed`。
- 真实载荷探测得到 64 条 adapter 范围外记录和 4 条缺失 key-version 的配置，详见 `artifacts/e4-source-payload-probe-20260907.json`；2 个用户需衔接 E3 canonical 身份，62 条 Skill 需按 E4 必要输入边界适配，不在本轮擅自扩大为 E6 完整发布。
- 回滚点：仅撤销新增 CLI、载荷模块、两处接线及对应回归；保留快照与成功/失败证据。未签发正式 preflight、未轮换凭据、未执行 live DDL/导入/停写/切换。
- 执行环境和敏感输出故障及已采取的控制如 `test-record.md` 所述；未删除源数据，Windows 虚拟环境已按锁文件恢复。
- 最终验证：定向 `38 passed`，全量 `470 passed, 1 warning`；Ruff/compileall/diff check 通过，文档 `195 files, 178 local links` 通过，真实源探测重放一致。补充合法续跑不会因缺少随包目标用户事实而被纯离线载荷检查误拒绝的回归；live 身份/FK 仍由受保护目标的权威查询验证。

## 历史变更表

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-09-02 | `plan.md` | 新建 E4 执行计划，固化范围、入口条件、非目标、任务、风险、退出和回滚门槛 | 将 E4/AR-3 共享理解落为阶段入口；保持待确认 | 仅新增文档；未改代码、schema、配置、数据库或外部资源 | 删除本批文档，不影响运行状态 | Codex | `E4-PREP-01` |
| 2026-09-02 | `source-inventory.md` | 建立 MySQL/Django/文件/MD5/图片/Chroma/Skill/Redis source inventory 格式，记录本地只读观察和正式纳入条件 | 防止把派生投影、sidecar 或默认资源误当业务权威 | 仅记录结构和观察；未连接在线资源 | 删除本批文档 | Codex | `E4-PREP-02` |
| 2026-09-02 | `identity-map-contract.md` | 固定 source key、canonical UUID、E3 用户 UUID5 兼容、digest/幂等/conflict/orphan 状态和未决策略 | 在迁移器实现前先冻结可重放身份规则 | 仅设计合同；未写 `migration_maps` | 删除本批文档；不影响现有数据 | Codex | `E4-PREP-03` |
| 2026-09-02 | `write-path-inventory.md` | 盘点 Django、FastAPI service、Chroma/MD5/图片、Skill Storage、Redis pending、job/runner 等写入口及目标处置 | 为 FastAPI 唯一写权威和停写窗口准备清单 | 仅静态分析；未禁用或改变任何入口 | 删除本批文档 | Codex | `E4-PREP-04` |
| 2026-09-02 | `rollback-runbook.md` | 建立 preflight、snapshot、dry-run、隔离演练、停写切换、验证和 restore-forward 模板 | 确保后续实施有可执行恢复边界 | 仅模板；未填真实 DSN/路径，未执行命令 | 删除本批文档 | Codex | `E4-PREP-05` |
| 2026-09-02 | `source-inventory.md`、`plan.md`、`test-record.md` | 补记 Chroma collection/metadata 用户身份冲突、临时路径脱敏和 Skill/配置来源边界；将冲突登记为待核验项 | 防止把派生标识、环境路径或未证明来源误当作可导入事实 | 仅更新准备文档；冲突仍未解决，未生成 mapping | 删除本批文档 | Codex | `E4-PREP-06` |
| 2026-09-02 | `identity-map-contract.md`、`write-path-inventory.md`、`plan.md`、`test-record.md`、`route-match-evidence.md` | 补齐 batch/entity/artifact digest、加密配置 key、媒体 SQL 表和 reranker/calibration 权威约束；登记 `PUT /note-template/reorder` 路由冲突并保存隔离复现 | 确保唯一写权威切换不会遗漏可执行入口或不可恢复密文/媒体，也不会混淆 digest 语义 | 未修改应用代码、配置或数据；待 E4 授权后修复并验证 | 删除本批文档；运行行为未改变 | Codex | `E4-PREP-07` |
| 2026-09-02 | `plan.md`、`identity-map-contract.md`、`source-inventory.md`、`test-record.md` | 对照现有 `migration_maps` 三态 check constraint，登记 E4 流程状态与多层 digest 的 schema 兼容门槛 | 防止迁移器写入未支持状态或把不同 digest 语义混在一个字段 | 仅文档审阅；未执行 DDL、未写 mapping 或业务数据 | 删除本批文档；现有 schema 未改变 | Codex | `E4-PREP-08` |
| 2026-09-02 | `backend/app/router/note_template_router.py`、`backend/tests/test_note_template_route_matching.py` | 将具体 `PUT /note-template/reorder` 路由移到 `/{template_id}` 之前，并加入纯路由匹配回归 | 修复已登记的写入口冲突，避免静态路径被当作模板 ID | 仅改变路由注册顺序；未调用数据库或业务 API | 恢复原注册顺序（同时恢复已知缺陷）；不影响数据 | Codex | `E4-ROUTE-01` |
| 2026-09-03 | `backend/app/db/e4_guard.py`、`backend/tests/test_e4_guard.py`、`artifacts/local-inventory-v3.json` | 恢复准备后让纯 `E4Target` tuple/list 输入逐项经过同一字段校验；补记端点大小写规范化、DSN host 大小写匹配回归，并复核脱敏本地 manifest | 防止内部已解析输入绕过 allowlist 校验；为后续真实拓扑 preflight 保持 fail-closed | 仅修改守卫校验/本地测试和证据索引；未连接或写入任何业务资源 | 回退本次守卫补丁；保留 v2/v3 脱敏 manifest 作为历史证据，不影响业务数据 | Codex | `E4-PREP-09`；manifest canonical `7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac` |
| 2026-09-03 | `backend/app/e4/identity.py`、`backend/tests/test_e4_identity.py` | 修正 `IdentityDecision` artifact digest 传递；标准 UUID source ID 规范化后保留为 target UUID；Django `user` 保持大小写敏感 ShortUUID/E3 UUIDv5；既有 mapping 复用 target UUID 时 fail-closed；报告输出 artifact digest 并验证摘要自洽 | 防止身份 dry-run 构造错误、错误 casefold Django 身份、target UUID 劫持和 digest 语义丢失 | 仅离线解析/报告逻辑与测试变更；未写 `migration_maps` 或业务表 | 回退本次身份模块/测试补丁；不影响外部资源 | Codex | `E4-PREP-11` |
| 2026-09-03 | `backend/app/db/e4_guard.py`、`backend/tests/test_e4_guard.py`、`backend/ops/e4/` | 补齐专用数据库账号和精确 DSN query 校验；按迁移用途强制 E4 migration switch、approval token 和 container ID/network/image/port/health 拓扑事实；preflight 支持显式 container inspector；缺失 database fact 不再默认放行 | 让迁移/恢复/切换 guard 真正绑定批准资源，同时保留 inventory/dry-run 的离线最小路径；不对 3306 增加特殊监听规则 | 仅 guard、合成测试和隔离拓扑定义变更；compose 未启动，未建立连接 | 回退本次 guard/compose/测试补丁；不删除任何资源或证据 | Codex | `E4-PREP-11`；`backend/ops/e4/README.md` |
| 2026-09-03 | backend test gate | 重跑 E4 identity/guard/inventory/route 定向测试及后端全量测试、Ruff、`compileall`、`git diff --check`、Compose config 和文档链接检查 | 验证本轮补丁无回归并保留可审计证据 | `37 passed` 定向；`391 passed` 全量；静态/Compose/文档门禁通过；无外部连接 | 保留测试体、失败现场和中间材料，按 Q22/Q34/Q43 在全部 E 阶段验收后统一清理 | Codex | `E4-PREP-11`、`E4-PREP-12` |
| 2026-09-03 | `backend/app/e4/identity.py`、`backend/app/db/e4_guard.py`、对应测试和 `backend/ops/e4/` | 审阅加固：legacy 显式 target UUID 必须符合确定性 E4 UUIDv5；preflight purpose 按 source/target/restore 角色限制；allowlist 精确绑定专用数据库账号；声明拓扑的资源必须由独立 container inspector 提供事实；target/restore 使用分离凭证，Compose 文档与端口/数据库命名一致 | 防止手写 UUID 劫持、跨角色误授权、DSN 账号漂移、数据库 inspector 伪造容器事实和 target/restore 凭证复用 | 仅离线守卫/身份合同、测试夹具和隔离拓扑文档变更；未启动 Compose，未连接真实资源 | 回退本次 `E4-PREP-13` 代码/测试/拓扑补丁；保留失败现场和历史证据 | Codex | `E4-PREP-13` |
| 2026-09-03 | E4 local test gate | 当前工作树；无外部拓扑 | verified-local | 定向回归：`pytest -q tests/test_e4_guard.py tests/test_e4_identity.py tests/test_e4_inventory.py tests/test_note_template_route_matching.py` | 关键负向门禁全部通过；不得连接或写入真实资源 | 过程成功点 `40`、`42`、`43`、`47` passed；移除超出架构要求的 source/server 独立限制后最终 `46 passed in 0.79s`；未建立网络/数据库连接 | 通过；E4-01 至 E4-08 仍保持 `not-run` | pytest 输出；`test-record.md` | Codex | `E4-PREP-13` |
| 2026-09-03 | E4 full local gate | 当前工作树；无外部拓扑 | verified-local | 加固后运行 `uv run pytest -q`、Ruff、`compileall`、`git diff --check`、Compose `config --quiet` 和文档链接检查；Compose 首次未注入变量时保留拒绝现场，再以一次性占位变量重跑 | 全量测试/静态/Compose/文档门禁 exit 0；不得启动容器或建立数据库/网络连接；禁止记录凭证值 | 首轮 pytest `394 passed, 1 warning`；最终门禁首次出现既有 runner 取消/lease 竞态 `395 passed, 1 failed`，该单测随后连续 8 次通过，完整复跑最终 `396 passed, 1 warning`；Ruff/compileall/diff/docs 通过（`195 files, 178 local links`）；Compose 未注入变量按预期拒绝，注入本地占位值后 `config --quiet` 通过；未启动容器 | 通过；所有失败现场和复跑上下文保留，E4-01 至 E4-08 仍 `not-run` | pytest 输出；Compose 命令输出；`test-record.md` | Codex | `E4-PREP-14` |
| 2026-09-03 | `backend/app/db/e4_guard.py`、`backend/tests/test_e4_guard.py`、`backend/ops/e4/README.md` | 复核其他执行者的 E4 工作树；将容器型 preflight 的独立 topology inspector 和事实匹配置于 database inspector 前，并证明缺失/漂移时数据库检查器零调用；重跑最终门禁 | 防止在容器身份、镜像、网络、端口或健康状态尚未验证时先连接 allowlist DSN | 仅离线 guard、测试和操作说明变更；未对已存在 E4 Compose 执行 mutation，未建立数据库连接、执行 DDL 或写入 | 回退本次检查顺序、断言和说明；不影响业务数据或既有证据 | Codex | `E4-PREP-15`；定向 `46 passed`；最终全量 `400 passed, 1 warning`；静态/Compose/文档门禁通过 |
| 2026-09-03 | `artifacts/e4-topology-observation-20260903.json`、`plan.md`、`rollback-runbook.md`、`test-record.md` | 发现其他执行者已启动两个 E4 Compose 容器；只读记录 container/image/network/loopback port/volume/health 及各自 `auto.cnf` server UUID，并更正当前状态 | 防止继续以“Compose 未启动”的错误前提推进，同时为正式 allowlist 保留非秘密身份事实 | 只读 Docker 元数据和容器文件观察；未读环境变量/凭证，未连接 MySQL，未启动、停止或重建资源 | 删除本观察记录和状态补记不会改变运行资源；容器本身由后续获授权的资源操作单独处置 | Codex | `E4-PREP-16`；verified-live；artifact SHA-256 `1c96e6355a646edde68a4eabd229043a1332009308a510a10c02f4c7f71ec946` |
| 2026-09-03 | `backend/app/db/e4_guard.py`、`backend/tests/test_e4_guard.py`、`backend/ops/e4/README.md` | 将 migration approval token、TTL 和已记录 preflight 的静态有效性检查前移到所有 injected inspector 之前；补充无效输入下检查器零调用回归 | 避免缺审批、非法 TTL、过期或篡改记录触发不必要的容器探测或数据库连接 | 仅 guard、合成测试和说明变更；已存在 E4 容器未参与测试，未连接数据库 | 回退本次门禁顺序和对应断言；不影响运行资源或业务数据 | Codex | `E4-PREP-17`；定向 `46 passed`；全量 `400 passed, 1 warning`；静态门禁通过 |
| 2026-09-03 | `backend/app/db/e4_guard.py`、`backend/tests/test_e4_guard.py`、`backend/ops/e4/README.md` | 移除 `load_guard_from_config` 的静态 `container_facts` 注入旁路；容器型 guard 必须先通过记录静态校验，再由显式 live inspector 复核；增加篡改记录、缺 inspector、旧参数注入、health 漂移和成功消费回归 | 使运行时消费接口与“签发和消费均须 fresh inspection”的操作合同一致，避免把已记录或调用方静态事实误当当前拓扑 | 仅 guard 接口、合成测试和说明变更；只读复核现有 Docker 拓扑，未连接 MySQL、执行 DDL 或改变容器 | 回退本次接口、测试和说明；不影响运行资源或业务数据 | Codex | `E4-PREP-18`；定向 `46 passed`；全量 `400 passed, 1 warning`；E4 范围静态门禁通过；根范围 Ruff 既有失败另行保留 |
| 2026-09-05 | `backend/alembic/versions/20260905_0008_e4_business_shadow.py`、`backend/app/models/*.py`、`backend/tests/test_migration_contract.py` | 正式执行 `E4-03`：新增 additive/shadow Alembic revision，补齐 canonical UUID、owner、content/artifact digest、key-version、媒体 SQL 表及 E4 批次/实体旁表；加入 ORM/revision 约束合同回归 | 在最终数据库中保留旧主键和旧输入，提供可重放的 canonical 身份、分层 digest、受控状态和 SQL 业务权威承载 | 仅修改代码与隔离合同；未在 live 数据库执行 DDL，未改变真实业务表或数据；实现先标 `待验证` | 回退本 revision、模型和合同测试；不得对 populated 数据库执行未经批准的 downgrade | Codex | `E4-03`；revision `20260905_0008_e4_business_shadow`；完整本地门禁 `408 passed, 1 warning`，Ruff/compileall/diff/docs 通过 |
| 2026-09-05 | `backend/app/e4/repository.py`、`backend/tests/test_e4_repository.py`、`backend/app/models/e4_migration.py` | 正式执行 `E4-04` 离线部分：实现批次/实体幂等、状态机、owner/mapping target/digest 不可变、冲突和状态转移 audit correlation、UoW rollback 和 SQL 媒体字节重放 | 使导入器在隔离 fixture 中可重放、可审计且不会覆盖既有 mapping 或跨 scope 合并 | SQLite 隔离 fixture 只写临时数据库；未写真实 `migration_maps` 或业务表。2026-09-05 topology recheck 显示 target/restore 已退出、网络无连接且正式 allowlist/credential/backup/schema 权限事实缺失，live preflight 阻塞 | 保留 fixture 和失败现场；live 资源不得通过猜测凭证或重建容器推进 | Codex | `E4-04`；`backend/tests/test_e4_repository.py`；`artifacts/e4-topology-recheck-20260905.json`；完整本地门禁 `408 passed, 1 warning`；离线实现先标 `待验证` |
| 2026-09-05 | `backend/app/db/transaction_context.py`、`backend/app/db/db_config.py`、`backend/app/db/uow.py`、`backend/app/services/*.py`、`backend/app/skills/service.py`、`backend/app/services/note_service.py` | 正式执行事务边界收尾：请求/UoW session 只 flush，由 owning transaction 统一 commit；注册 post-commit callback；笔记 Chroma 写入/删除和自动标注延迟到提交成功后；Skill registry refresh 只在提交后发布；post-commit cancellation 被视为投影失败并记录 | 消除 SQL 事实与外部投影的事务分裂，确保回滚不会留下 Chroma/registry 副作用，且投影失败/取消不伪装成业务回滚 | 仅代码与隔离回归；未连接 MySQL/Redis/Chroma，未改变真实数据 | 回退事务上下文和服务补丁；保留旧测试/失败现场 | Codex | `E4-04`；`tests/test_skill_service_transactions.py`、`tests/test_note_service_transactions.py`；全量 `419 passed, 1 warning` |
| 2026-09-05 | `backend/app/e4/repository.py`、`backend/tests/test_e4_repository.py` | 收紧媒体重放语义：同一 source key 或同一 scope/content digest 的完全相同媒体可跨 migration batch 幂等重放；仍校验字节、artifact/content digest、MD5、owner、元数据和状态漂移 | 迁移批次是审计上下文，不应把完全相同的 SQL 业务资产重放误判为事实冲突 | 仅 SQLite fixture 与回归测试；真实媒体表未写入 | 回退媒体 immutable 比较/测试补丁；不影响外部资源 | Codex | `E4-04`；`tests/test_e4_repository.py::test_media_bytes_are_sql_authoritative_and_replayable`；相关 E4 测试 `14 passed` |
| 2026-09-05 | `backend/app/e4/importer.py`、`backend/scripts/e4_import.py`、`backend/tests/test_e4_importer.py`、`backend/tests/test_e4_cli.py` | 正式执行 `E4-04` 收口：finalize 前核对 bundle 全量实体，缺少前置批次时 fail-closed；quarantine 结果显式 blocked；CLI 停止后续 chunk 并返回非零码 | 防止 partial batch 被错误标记为 imported，或把密文 key-version quarantine 当成成功 | 仅 SQLite 隔离 fixture、CLI 合同测试和代码；未连接 MySQL/Redis/Chroma，未写真实业务数据 | 回退 importer/CLI 保护和回归测试；保留 partial-finalize/quarantine 失败现场 | Codex | `E4-04`；定向 `14 passed`；包含 partial-finalize、two-chunk success、quarantine blocked 和 CLI 返回码回归 |
| 2026-09-05 | E4 local verification gate | 重跑后端完整 pytest、Ruff、compileall、diff check 和文档链接检查 | 确认正式 E4 改动无本地回归并固定可审计证据 | `428 passed, 1 warning`；Ruff/compileall/diff/docs 通过；未连接真实资源；历史瞬时 job-runner 失败现场继续保留 | 保留测试体、warning、瞬时失败和 live blocker 证据 | Codex | E4-03/E4-04；`test-record.md` |
| 2026-09-05 | `backend/app/services/database_session_manager.py`、`backend/tests/test_database_session_manager_transactions.py` | 正式执行 `E4-04` 事务边界收尾：会话新增、摘要、追加、更新、消息删除和会话清理统一经 `persist_service_write`；helper 对 managed/UoW session 延迟 owning commit，独立调用保持兼容持久化 | 消除剩余直接 service commit 写入口，避免会话事实与事务 ownership 分裂 | 仅 SQLite 隔离 fixture；七次写路径调用均经过 helper，未连接或写入真实数据库 | 回退 helper 调用和隔离回归；不影响外部资源或历史数据 | Codex | `E4-04`；定向 `1 passed`；完整 `428 passed, 1 warning` |

## 明确未做

- 未连接、读取或修改现有业务 MySQL、Django 在线数据库、Redis 或 Chroma 服务。
- 未执行 `mysqldump`、业务 migration、Alembic populated DDL、停写、FastAPI/Django 权威切换或任何删除/GC。
- 未在真实业务数据库生成或写入 E4 `migration_maps`、业务目标表、audit/job 结果或 Chroma generation；SQLite fixture 的临时写入仅用于本地回归。
- 已新增 E4 Alembic revision、ORM shadow 字段、受控旁表、媒体 SQL 模型和 repository；但未在 live 数据库执行 DDL、未修改真实业务 schema/数据或外部资源。
- E2/E3/E1 容器、volume、network、证据和凭证未复用、未启动、未清理。
- 本机身份未确认的 `mysqld.exe` 进程未探测、未连接、未复用；视为受保护的未知现有资源。

## 后续记录规则

每个实施变更必须关联一个 `E4-*` 任务、一个回滚点和一个证据 ID；实现完成先标 `待验证`，不得由实现者直接标 `已关闭`。任何 source digest 漂移、unknown/orphan、双写、审计缺字段或恢复失败都要单独记录为 `阻塞`。

## 清理与保留（Q22/Q34/Q43）

阶段内不清除测试体、失败现场或可重建中间材料；成功、失败、无效和历史证据均保留并单独标注。所有 E 编号阶段完成并经最终验收后，统一执行一次清理：删除原始敏感 source、临时 fixture、可重建中间体和完整环境快照；保留脱敏 manifest/inventory、审计、摘要、错误报告、备份、restore-forward 和回滚证据。旧输入、未对账源和健康快照不得因本规则提前删除。

## 本次审阅补充

- `scripts/check-docs.ps1`：`Markdown checks passed: 194 files, 178 local links.`
- 本地 route-match 复现仅使用 backend `.venv` 和合成 allowlist URL；没有建立数据库或外部服务连接。
- 用户 Q41 确认由当前执行者接手；Q42 确认按文档执行；Q43 要求沿用 E0-E3 的三件套、证据状态、restore-forward 和最终清理规则。

## 2026-09-03 暂停/恢复收口

- 上一轮按用户要求暂停并完成记录收口；本轮仅恢复 E4 准备，不进入真实业务迁移。
- `E4-PREP-09` 已完成：`22 passed`；Ruff、Python `compileall`、`git diff --check` 和文档检查均通过（`194 files, 178 local links`）。
- 本地 v3 manifest：采集时间 `2026-09-03T01:07:41.099399+00:00`，4 collections/88 embeddings、MD5 7 records/7 values、图片 0 files、Skill objects 10，2 个脱敏 `scope_conflict`。
- 工具定义的 manifest canonical digest（排除 `captured_at` 和自身摘要字段）为 `7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac`；封装 JSON 文件 SHA-256 为 `8c018624c28192a7e84000ca6b1f455d08ee57d172a6c81792d9cf7058bf7faf`，两者不可混用。
- 仍未连接 MySQL/Django/Redis/Chroma，未执行 DDL、mapping 写入、停写、切换、删除或 GC；`E4-01` 在线/正式业务部分保持 `not-run`。
- `E4-PREP-10`：身份 dry-run 将无 source metadata 的既有 target 明确归类为 `target_exists_without_mapping`，canonical UUID 显式拒绝大写；E4 guard/identity/inventory/route 定向回归 `30 passed`，相关 Ruff 检查通过。未连接真实资源。

## 2026-09-05 正式执行收口

- 按用户最新指令停止 prep，正式执行 `E4-03`/`E4-04` 代码改动；不再新增 `E4-PREP-*` 编号，历史 prep 记录仅保留为过程证据。
- `E4-03` 已完成 revision、ORM、约束合同和本地 schema parity 实现，状态为 `待验证`；尚未执行 live Alembic DDL 或逐表业务对账。
- `E4-04` 已完成离线 repository/fixture 实现，状态为 `待验证`；live preflight 为 `阻塞`。recheck 证据显示两个容器 `Exited (255)`、E4 network 无连接、restore 历史账号与当前 compose 不一致，且正式 allowlist、credential reference、backup location、schema/权限事实缺失。
- 本次未读取凭证、未连接 MySQL/Django/Redis/Chroma，未启动/停止/重建容器，未停写、切换、删除或 GC。中间测试体按 Q22/Q34/Q43 保留，待所有 E 阶段最终验收后统一清理。
