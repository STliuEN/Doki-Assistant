# 安全与可靠性加固计划

状态：基础工作包 `1-6` 已完成；剩余风险继续跟踪

审查日期：2026-07-16

最近复核：2026-08-18

适用范围：当前 `ai_document_assistant` 分支

本文记录安全、认证、数据库演进和接口合同的当前事实与剩余风险。[改进执行计划](./improvement_execution_plan.md) 维护可选工作包和完成状态，[全量重构开发计划](./roadmap_next.md) 维护长期阶段与依赖，[开发与运行说明](./development_setup.md) 维护实际命令和部署边界。历史实施证据位于 `project_changes/`。

工作包 `1-6` 已关闭最初审查中的路径穿越、原始 HTML 渲染、token 生命周期、固定测试账号、宽松生产 CORS、启动期 schema 修改和 API/SSE 合同漂移等问题。项目仍缺少生产部署编排、TLS/反向代理演练、统一服务端网络出口策略和完整备份恢复演练，因此不能仅凭本轮完成状态宣称公网就绪。

## 已验证基线

| 检查 | 2026-08-18 最终复跑结果 |
|------|--------------------|
| Backend pytest | `118 passed` |
| Backend Ruff | passed |
| FastAPI OpenAPI | current |
| Alembic | `20260817_0001 (head)`；offline SQL 生成通过 |
| Django system check / migration drift | passed；`No changes detected` |
| Django tests | 隔离 SQLite 与 LocMemCache，`19 passed` |
| Frontend Vitest | `20 passed` |
| Frontend lint / build | passed |
| Offline Benchmark | smoke `4/4`；regression `117/117`，无 hard veto |
| 浏览器认证流程 | 注册 `201`、资料读取 `200`、注销 `200`；注销后认证状态清空；桌面/移动端无重叠 |

2026-08-18 复跑补记：离线 smoke `4/4`、regression `117/117`（hard veto `0`），OpenAPI、Ruff 与 Alembic offline SQL 再次通过；未连接或修改现有 MySQL。

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
| API-01 | P1 | 已关闭 | canonical JSON 路由使用 `ApiResponse[T]`；OpenAPI 与真实 envelope 一致；SSE 固定 `schema_version: "1.0"` |
| REL-01 | P1 | 已关闭 | FastAPI 用户状态复核使用带 timeout 的异步 HTTP client，并有确定的依赖失败语义 |
| TEST-01 | P1 | 基础门禁已关闭 | 认证、路径、响应、SSE、迁移与限流合同已进入测试；更广的业务 E2E 继续由 R7 扩展 |
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
- FastAPI schema 由 Alembic 管理，baseline revision 为 `20260817_0001`，唯一约束与 ORM metadata 由合同测试比对。应用启动只检查 revision；实际升级必须显式执行 migration 命令。
- canonical JSON handler 通过泛型 envelope 发布真实 OpenAPI；成功响应不再用未验证的 `JSONResponse` 绕过模型。
- chat、knowledge、note 和 translate 的 SSE 都声明 `text/event-stream`，事件携带固定 `schema_version: "1.0"`。

## 剩余加固顺序

1. 完成 `NET-01`：为所有用户可配置外部地址统一 DNS 解析、重定向、loopback/private/link-local/cloud metadata 阻断和管理员 allowlist。
2. 完成生产反向代理、TLS、可信代理 header、日志脱敏、依赖漏洞与 secret scanning 演练。
3. 在不触碰现有数据的前提下制定 MySQL 备份、Alembic/Django migration dry-run、校验和恢复演练。
4. 随 R3 确认用户唯一标识、角色和审计模型；随 R6 完成头像及其浏览器测试。
5. 随 R7 扩展真实 MySQL/Redis/Chroma integration job 和注册、登录、聊天、上传、笔记、注销的完整 E2E。

## 公网就绪条件

只有同时满足以下条件，才能把文档中的“仅本地开发”限制改为支持公网部署：

- 所有 P0 风险保持关闭，剩余 P1 有明确接受或关闭记录。
- production profile 和反向代理/TLS 流程在干净环境演练通过。
- migration 可从空库执行，并对现有数据完成只读盘点、备份与恢复演练。
- 任意用户输入不能突破文件根目录或服务端网络出口策略。
- token 锁定、改密、注销、过期和刷新在 Django/FastAPI 间一致。
- Django、前端和跨服务认证测试进入稳定 CI required checks。
- 依赖漏洞扫描、secret scanning、监控告警和部署回滚清单已接入。
