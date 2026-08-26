# 安全与可靠性加固计划

状态：基础工作包 `1-6` 已完成；本地 A/B `SKILL-GATE`、可选 C 级 `EXEC-SKILL-GATE` 与公网/HA `PUBLIC-HA-GATE` 均未通过

审查日期：2026-07-16

最近复核：2026-08-25

适用范围：当前 `ai_document_assistant` 分支

本文只记录已实施安全控制、剩余风险和公网安全条件。[架构重写计划](./architecture_rewrite_plan.md)维护阶段、门禁和当前队列，[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)维护 package/权限/runner 合同，[开发与运行说明](./development_setup.md)维护实际命令。历史实施证据位于 `project_changes/`。

工作包 `1-6` 已关闭最初审查中的路径穿越、原始 HTML 渲染、token 生命周期、固定测试账号、宽松生产 CORS、启动期 schema 修改和通用 API/SSE 合同漂移等问题；Skill 增量 OpenAPI/错误合同仍属于未关闭阻断。项目仍缺少生产部署编排、TLS/反向代理演练、统一服务端网络出口策略和完整备份恢复演练，因此不能仅凭本轮完成状态宣称公网就绪。门禁必须分开解释：`SKILL-GATE` 只发布本地 A/B，`EXEC-SKILL-GATE` 只发布可执行 C 级，`PUBLIC-HA-GATE` 才允许公网/HA；公网启用 C 时才额外依赖 `EXEC-SKILL-GATE`。

## 已验证基线

| 检查 | 2026-08-24 最终复跑结果 |
|------|--------------------|
| Backend pytest | `216 passed` |
| Backend Ruff | passed |
| FastAPI OpenAPI | 生成/漂移检查通过；已知 Skill import/export/error schema 仍待修复 |
| Alembic | `20260824_0002 (head)`；upgrade/downgrade offline SQL 通过 |
| Django tests | 隔离 SQLite 与 LocMemCache，`19 passed` |
| Frontend Vitest | `6 files / 28 tests passed` |
| Frontend lint / build | passed |
| Offline Benchmark | smoke `4/4`；regression `117/117`，无 hard veto |
| 静态/依赖 | compileall、`uv lock` 和 requirements 检查通过 |
| 文档/差异 | `143 files / 132 local links`；`git diff --check` 通过 |

2026-08-24 复跑确认：OpenAPI、Ruff、compileall、lock/requirements、Alembic 双向 offline SQL、前后端测试和离线 Benchmark 均通过；未连接或修改现有 MySQL。

数据库验证仅使用临时 SQLite、Alembic offline SQL 和 revision 检查，没有连接或修改现有 MySQL。浏览器验收也未启动 FastAPI，未读取业务 MySQL。

## 风险状态

| ID | 优先级 | 状态 | 当前控制或剩余工作 |
|----|--------|------|--------------------|
| SEC-01 | P0 | 已关闭 | 知识库图片路径统一经过 containment helper；根、用户、MD5 和文件层均拒绝 symlink/junction；批量读取限制 100 个文件、25 MiB |
| SEC-02 | P0 | 已关闭 | 已移除 `rehypeRaw`；流式与历史消息使用同一 `ChatMarkdown`，危险 URL 被过滤 |
| AUTH-01 | P0 | 已关闭 | 使用 access/refresh token 对、固定类型与 claim、refresh 轮换、用户状态及 token version 校验 |
| AUTH-02 | P1 | 已关闭 | Redis 使用确定性撤销键，不调用 `KEYS`；撤销存储故障 fail closed 并返回 `503` |
| AUTH-03 | P1 | 已关闭 | Zustand 是前端单一认证来源；`401`、注销和刷新失败完整清理 token、用户信息和登录状态 |
| DEPLOY-01 | P0 | 已关闭 | 启动不再创建固定账号；开发账号只能用显式 `seed_dev_user --password ...` 创建，登录页无内置凭据 |
| DEPLOY-02 | P0 | 已关闭 | Django/FastAPI 拒绝未知 `ENV` 并使用明确 CORS allowlist；生产弱密钥、DEBUG、空 host/origin 或通配 origin 会 fail fast |
| DB-01 | P0 | 已关闭 | Django migration 已纳入版本控制，CI 检查 migration drift，启动不生成或执行 migration |
| DB-02 | P0 | 已关闭 | FastAPI Alembic baseline 含 ORM 唯一约束并有 metadata 合同检查；启动只校验 revision，不执行通用 schema DDL |
| API-01 | P1 | 通用基线已关闭；Skill 增量保留 | canonical JSON 通用路由使用 `ApiResponse[T]`，SSE 固定 `schema_version: "1.0"`；Skill 路由的虚假 `200 Any`、ZIP media type 和错误响应仍由 `SKILL-03` 阻断 |
| REL-01 | P1 | 已关闭 | FastAPI 用户状态复核使用带 timeout 的异步 HTTP client，并有确定的依赖失败语义 |
| TEST-01 | P1 | 基础门禁已关闭 | 认证、路径、响应、SSE、迁移与限流合同已进入测试；更广的业务 E2E 继续由 R7 扩展 |
| SKILL-01 | P0 | 部分关闭，三类门禁均未通过 | 标准 package/Storage、版本回滚、CapabilityGrant、SkillRunBinding、private 过滤、revision/outbox、资源编辑和旧目录退出已有局部实现/测试，但授权闭环与多实例收敛未由真实环境证明；仍缺 durable import、per-user scope、grant revoke/角色分离、Tool/MCP policy digest、累计 token 预算、Legacy 对账和完整真实 E2E |
| SKILL-02 | P0 | 保留 | 旧运行目录已在通用 `LegacySkillMigrator` 和逐项对账前删除；seed package 只能恢复已知基线，不能证明历史别名、用户修改、安装设置和 Tool/MCP binding 已迁移 |
| SKILL-03 | P0 | 保留 | 发布原子性、单包隔离、`installed_disabled`、staging TTL/orphan GC、完整审计，以及 `409`/`413`/恶意 ZIP/CORS 合同尚未形成真实数据库/API/浏览器发布门 |
| EXEC-01 | 条件 P0（启用 C 时） | 未实现 | AR-1 尚未交付语言无关隔离进程协议和恶意测试桩；SK-4 Node/Python adapter、沙箱、依赖锁定、grant、取消和进程树终止均未通过 `EXEC-SKILL-GATE`；C 保持禁用时不阻断本地 A/B |
| PLATFORM-01 | P1 | 保留 | backend lock/uv resolution 与 CI 当前仅支持 Windows；没有 Linux lock、平台依赖拆分或 Windows/Linux conformance matrix，不能声明 Linux/macOS 支持 |
| PUBLIC-01 | P0 | 保留 | 反向代理/TLS、可信代理、secret/漏洞扫描、监控告警、备份恢复、canary/rollback 和组合故障证据未通过 `PUBLIC-HA-GATE` |
| NET-01 | P1 | 保留 | 自定义模型/Embedding 地址仍需统一 DNS、重定向和私网地址 egress 策略 |
| USER-01 | P1 | 保留 | 登录主标识及 username/email 唯一性仍需结合后续用户域收敛确认 |
| UI-01 | P2 | 保留 | 头像选择、上传、失败反馈与组件测试仍不是完整浏览器主流程 |

## 已实施控制

### 文件系统边界

- `md5`、文件名和扩展名在进入文件系统前校验，解析后的路径必须位于当前用户图片根目录内。
- 单文件读取、批量读取、提取和删除复用同一 containment 规则；读接口不会为缺失路径创建目录。
- 普通图片之外的文件被过滤；批量接口有数量和总字节预算。
- 回归覆盖 `..`、反斜杠及编码形式、绝对路径、Windows 盘符、跨用户访问和 symlink/reparse point。

### 前端内容与认证状态

- 原始 HTML 不进入聊天 DOM；标准 Markdown、代码、表格和安全链接保持可用。
- Axios、SSE、路由守卫和用户状态统一读取 Zustand 中的 access/refresh token。
- 并发 `401` 只触发一次 refresh；轮换成功后更新 token 对，失败后原子清理认证状态。
- token 目前仍由前端持久化。将来如迁移到 `HttpOnly`/`Secure`/`SameSite` cookie，必须同时设计 CSRF、SSE 和跨服务代理合同。

### Token 生命周期

- Django 签发 access/refresh token 对，严格校验签名、`iss`、`aud`、`jti`、`sid`、`token_type`、`ver` 和过期时间。
- refresh token 每次使用后轮换，旧 token 重放被拒绝；密码重置递增 `token_version`，使旧 token 失效。
- FastAPI 只接受 access token，并要求非空 `user_id/token_type/iss/aud/jti/sid`、整数 `ver/iat/nbf/exp`，再复核撤销状态和短 TTL 用户状态缓存。
- 注销撤销相关凭据。Redis 撤销存储不可用时，受保护接口、refresh 和 logout 采用 fail closed，返回 `503` 而不是放行。
- Django 与 FastAPI 共同校验 `contracts/auth_access_token.json`，防止跨服务 claim 或算法漂移。

这是破坏性认证升级：旧的无类型 JWT 不再有效，部署后用户必须重新登录。兼容响应暂时保留原 `token` 字段，同时返回 refresh token 和对应过期信息。

### 部署与限流

- Django 启动不再建库、运行 `makemigrations`/`migrate` 或创建账号；FastAPI 使用 lifespan 管理资源，不在启动时修改 schema。
- Django production profile 要求 `DEBUG=False`、非空 `ALLOWED_HOSTS`、可信 CORS origins、强 JWT secret 和 Redis cache URL。
- FastAPI production profile 要求 `DEBUG_MODE=false`、强且分离的 JWT/模型配置密钥、显式 `JWT_REDIS_URL` 和非空、非通配 CORS allowlist；SSE 不写路由级通配 origin。
- Django 登录、注册和 refresh 使用独立固定窗口限流；FastAPI 用单个 Redis Lua 脚本创建/递增计数并保证 TTL。缓存故障按安全策略返回 `503`。
- `ENV=test` 强制 Django 使用 LocMemCache，避免测试误用本机 Redis。

### 版本化迁移与 API/SSE 合同

- Django migration 源文件进入版本控制；CI 执行 system check、migration drift 和隔离测试。
- FastAPI schema 由 Alembic 管理，当前 head 为 `20260824_0002`；baseline 与 Skill domain revision、唯一约束及 ORM metadata 均由合同测试比对。应用启动只检查 revision；实际升级必须显式执行 migration 命令。
- canonical JSON handler 已建立泛型 envelope 基线，普通成功响应不再用未验证的 `JSONResponse` 绕过模型；Skill 增量路由仍须移除虚假 `200 Any` 并补准确的 ZIP/error schema。
- chat、knowledge、note 和 translate 的 SSE 都声明 `text/event-stream`，事件携带固定 `schema_version: "1.0"`。

## Skill、执行与发布边界

门禁范围、阶段依赖和当前队列以[架构重写计划](./architecture_rewrite_plan.md)为准；package、授权、发布、迁移和 runner 的详细合同以[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)为准。本风险计划只保留以下安全结论：

- 未通过可选 C 级门禁时，含脚本或 runtime 未就绪的包只能保持 `installed_disabled`，不得启用、路由或执行。
- Skill 管理与安全审批必须分权；grant revoke、Tool/MCP policy digest、发布事务、单包隔离、审计和 GC 任一项未闭环，都不能声明 A/B 发布安全。
- 旧运行目录提前删除不等于迁移完成；必须从只读历史输入离线对账，不得为了补证据恢复 Legacy runtime。
- 当前 lock 和 CI 只能支持 Windows 声明；没有对应平台 lock、依赖拆分和 conformance 证据时，不得声明 Linux/macOS 支持。
- Skill API 仍须用真实 API/浏览器测试固定 `409/413`、ZIP media type、结构化恶意 ZIP 错误和 CORS fail-closed 行为。

## 风险处置原则

- `SKILL-01` 至 `SKILL-03`、`PUBLIC-01` 等 P0 未关闭时，相关门禁保持未通过；不得用已有代码切片或绿色单元测试替代真实依赖与恢复证据。
- 当前实现顺序只从架构重写计划读取；本文件不维护第二套 AR/SK 队列。
- `NET-01` 必须由统一服务端 egress policy 处理，默认阻断 loopback、private、link-local、cloud metadata、危险重定向和 DNS 漂移。
- 公网部署是本地架构完成后的独立决策；没有明确拓扑、容量目标和运维责任人时，不启动公网/HA 验收。

## `PUBLIC-HA-GATE` 公网就绪条件

只有同时满足以下条件，才能把文档中的“仅本地开发”限制改为支持公网部署：

- 所有 P0 风险保持关闭，剩余 P1 有明确接受或关闭记录。
- production profile 和反向代理/TLS 流程在干净环境演练通过。
- migration 可从空库执行，并对现有数据完成只读盘点、备份与恢复演练。
- 任意用户输入不能突破文件根目录或服务端网络出口策略。
- 本地 A/B `SKILL-GATE` 必须已通过，旧内置 Skill runtime 必须已退出且 Legacy 离线迁移/不可恢复差异已有批准记录。
- 若公网只启用 A/B，C 包必须保持 `installed_disabled`，不要求 `EXEC-SKILL-GATE`；若公网开放任何 C 级安装启用、构建或执行入口，对应平台的 `EXEC-SKILL-GATE` 必须已通过，package、依赖和脚本不得突破 worker 文件/网络/资源边界。
- token 锁定、改密、注销、过期和刷新在 Django/FastAPI 间一致。
- Django、前端和跨服务认证测试进入稳定 CI required checks。
- 依赖漏洞扫描、secret scanning、监控告警和部署回滚清单已接入。
- 生产 CORS 只允许审阅过的 origin；Skill 导入、导出、资源预览和 SSE 的预检/凭据场景均有浏览器测试，不能用 `*` 与 credentials 组合。
- 真实 MySQL/Redis/Storage/Chroma 的备份、PITR/恢复、对账、API/worker 回滚、canary 自动 abort 和组合故障演练达到批准的 RPO/RTO/SLO。
- 当前 Windows-only lock/CI 只能支持 Windows 部署声明；任何 Linux 公网/HA 声明必须先具备 Linux lock、平台依赖拆分和 Windows/Linux required-check matrix。
