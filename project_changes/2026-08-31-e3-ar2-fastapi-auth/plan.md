# E3/AR-2/S2 FastAPI 认证、会话、撤销、角色与审计

日期：2026-08-31  
状态：待你确认  
负责人：Codex  
审阅/批准人：用户  
用户确认：用户已完成 E3 设计质询并要求先制作本计划材料；本文件完成后等待最终执行口令。  
执行口令：`开始执行e3`（这是本 E3 批次的唯一执行授权口令，不表示重新执行已关闭的 E2）

## 0. 当前执行纪律

本批当前只完成计划材料，不执行以下任何动作：

- 不修改应用代码、Alembic revision、OpenAPI 或前端实现。
- 不读取项目 `.env`，不连接当前 Django/MySQL/Redis/Storage/Chroma。
- 不创建、启动、停止或清理容器、volume、network。
- 不导入用户、密码 hash、session 或 token，不执行 migration、切换 proxy 或认证写权威。
- 不接受“开始执行 E2”“开始实施”等替代文本；只有用户明确发出 `开始执行e3` 后才进入实施。

本阶段的两次大确认如下：

1. **执行确认**：用户审阅本计划并明确发出 `开始执行e3`。该口令一次性授权本计划列出的本地开发闭环，但不授权公网、HA、生产加固、E4 业务迁移或其他阶段。
2. **验收确认**：实现和证据完成后，先保持 `待验证`，由用户审阅验收证据并明确确认关闭；未确认不得标记 `已关闭`。

## 1. 背景与当前事实

E3 对应 `E3 = S2 = AR-2`，入口是已关闭的 E2/AR-1 SQL foundation。当前权威阶段顺序和 E3 责任边界见：

- `docs/architecture_rewrite_plan.md`
- `docs/architecture-execution-handoff-2026-08-26.md`
- `docs/architecture-target-blueprint-2026-08-26.md`
- `project_changes/2026-08-28-e2-ar1-sql-foundation/`

当前代码事实：

- `backend/app/models/identity_domain.py` 已有 `users`、`auth_sessions`、`refresh_tokens`、`token_revocations`、`roles`、`role_bindings` 和 `migration_maps` 目标结构，但这些表尚未接管真实认证行为。
- `backend/app/e2/auth.py` 是 E2 合成数据用的 `SyntheticAuthRepository`，明确不签发 token、不读取 Redis、不导入真实用户，不能当作 E3 runtime。
- `backend/app/utils/auth_utils.py` 当前解析 Django JWT，并通过 Redis 黑名单和 Django `/user/detail/` 校验 token 状态；管理员判定仍读取 YAML/环境变量并可读取 Redis/Django 用户资料。
- `backend/app/router/user.py` 当前只提供 FastAPI `/user/detail/`，资料读取仍依赖 Redis/Django；登录、注册、刷新、改密、更新和注销由 Django 服务提供。
- `front/vite.config.ts` 当前把 `/user` proxy 到 Django `18001`；E3 必须将公开 `/user/*` 入口切到 FastAPI。
- `DjangoUserService/apps/user/` 当前提供七个用户接口，Django `user_service` 表使用 ShortUUID 主键、PBKDF2 兼容 hash、`token_version` 和 Redis blacklist。
- E2 已关闭但其 source/restore 容器、volume、network 和证据必须保持原状，不作为 E3 目标。

## 2. 已冻结的用户决策

### 2.1 范围、授权和环境

- 只做本地开发档位，不做公网、HA、生产加固或 C 级 Skill。
- 计划获批后一次性授权完整本地开发闭环；验收是第二次大确认。
- 目标是完整接管 `register`、`login`、`reset-password`、`refresh-token`、`detail`、`update`、`logout`。
- E3 不执行 E4 业务数据迁移、E5 RAG、E6 Skill package 迁移或新产品工作包。

### 2.2 数据迁移与身份

- 只接受 Django 数据库只读 dump 或脱敏离线副本，不通过 Django 在线写路径迁移。
- 导入批准 dump 中的全部用户；固定 `migration_batch_id`、source digest，重复 dry-run 必须可复现。
- 重复邮箱/电话、无效邮箱、无效 hash、无法映射的 ShortUUID 或其他关键冲突均使整批 dry-run 失败；不自动合并、覆盖或猜测身份。
- 目标用户使用 canonical lowercase UUID；`migration_maps` 保存 `django/user/<ShortUUID> -> target UUID` 映射。
- 新增一对一 `user_profiles` 保存 `gender`、`bio`、`avatar` 引用和 `last_login`；E3 不搬运图片对象或文件权威。
- 新用户在匿名注册后立即为 `active`；E3 不做邮箱/短信验证和忘记密码邮件流。

### 2.3 Token、Cookie 和 session

- FastAPI 使用独立 `AUTH_JWT_SECRET`，不复用 Django 密钥；本地单机使用 HS256。
- access token 使用 Bearer JWT，包含 `sub=canonical UUID`、兼容字段 `user_id=同一 UUID`、`iss`、`aud`、`jti`、`sid`、`ver`、`exp`、`iat`、`nbf`。
- 旧 Django token 不接受；切换时强制重新登录。
- refresh token 为高熵 opaque token；原文只在 cookie 中短暂存在，SQL 只存 `token_digest`/`jti_digest`。
- refresh cookie 固定为 `doki_refresh`、`HttpOnly`、`SameSite=Strict`、`Path=/user/refresh-token/`；开发环境 `Secure=false`，不增加 CSRF token 或 Origin 中间件。
- access TTL 保持 15 分钟，refresh TTL 保持 30 天。
- 前端只在内存保存 access token；refresh 不进入 JSON 或 localStorage；Axios 使用 `withCredentials=true`。
- 允许多设备 session；普通 logout 撤销当前 session 和 refresh family；refresh replay 撤销整个 family；改密递增 token version、撤销旧 session 并签发新 session。
- session 支持列表和定向撤销；保存有界 `user_agent`、设备标签和不可逆 IP digest，不保存原始 IP。

### 2.4 角色、审批和旁路

- E3 只实现 `system/global` scope；角色为普通用户、`skill_admin` 和 `security_admin`。
- `skill_admin` 与 `security_admin` 必须是不同用户；不允许同一身份同时持有两种全局管理员角色。
- grant 准备者和批准者必须不同；安全管理员负责 grant approve/revoke，不能修改被批准对象。
- 紧急例外在本开发档位保持关闭；未来启用时需要短 TTL、双人复核和完整审计。
- 使用一次性 CLI，以两个不同的 active canonical UUID 分别 bootstrap 两个管理员，并在同一 SQL transaction 写 system bootstrap 审计；成功后禁止重复 bootstrap。
- 原有调试管理员读取旁路在 E3 验收前删除，不作为授权或验收证据。

### 2.5 Redis、错误和审计

- MySQL 是用户、session、refresh、revocation、role、grant 和 audit 的唯一正确性权威；Redis 不参与认证放行、撤销或 refresh 防重放。
- Redis 只可保留作非权威缓存/限流；开发环境可显式关闭限流，启用时 Redis 不可用返回明确 `503`，不能放行认证。
- 认证错误使用稳定 machine code，不枚举用户是否存在；响应包含 `code`、`message`、`data`、`correlation_id`，HTTP 语义使用 400/401/403/409/429/503。
- login/register/refresh/logout/password/profile/role/grant/revoke/bootstrap 的成功、失败和拒绝均写 append-only `audit_events`。
- 审计和日志不得出现明文密码、完整 password hash、access/refresh token、cookie、secret 或原始 IP。
- 每个请求生成或接收 `correlation_id`，并传播到 API、job、恢复和审计查询；审计查询只向 `security_admin` 或明确的本地运维身份开放。
- E3 不提供审计更新/删除接口；保留和擦除政策延期 AR-6。

## 3. 目标权威和切换拓扑

```text
浏览器/Vite 18080
       |
       v
FastAPI 18000  -- access JWT / SQL auth / SQL audit / SQL runner
       |
       v
E3 target MySQL 8.4（唯一认证写权威）

用户提供的 Django read-only dump --(dry-run/import)--> E3 target
                                      |
                                      +--> E3 restore（独立恢复目标）

Django 18001：仅内部 read-only/shadow adapter，不接受新写入
Redis：非权威缓存/限流，仅在显式开发配置启用
```

拟议资源名和端口仅在执行前通过 preflight 固定，不能直接使用当前业务目标：

| 用途 | 拟议资源 | 端口/数据库 | 边界 |
|---|---|---|---|
| E3 target | `doki-e3-20260831-mysql` | `127.0.0.1:33327` / `doki_e3` | 只接受批准的 E3 导入 |
| E3 restore | `doki-e3-20260831-mysql-restore` | `127.0.0.1:33328` / `doki_e3` | 只接受带 manifest 的 E3 bundle |
| E3 network | `doki-e3-20260831-net` | Docker bridge | 只连接上述两个容器 |
| E2/E1 资源 | 已存在资源 | 原端口和状态不变 | 禁止复用、启动、修改或清理 |

执行前必须同时满足：资源名、loopback 端口、数据库名、server UUID、镜像版本、网络成员和 source/restore 路径均在本批 allowlist；任一漂移立即停止并标记 `阻塞`。

## 4. Schema 与服务合同

### 4.1 E3 目标 schema 变更

E2 已提供身份表骨架；E3 只增加认证行为所需的加法式结构，不改写 E4 业务表的 populated user_id：

1. 新增 `user_profiles`：`user_id` 唯一 FK、资料字段、UTC timestamps；用户删除策略为 owned profile `CASCADE`，不保存图片 BLOB。
2. 为 `auth_sessions` 增加有界 session 识别字段，或建立等价一对一 metadata 表：`user_agent`、`device_label`、`ip_digest`；不得存原始 IP。
3. 新增通用 `authorization_grants`（或等价明确命名的 grant service 表）承载 target、scope、requested/approved/revoked actor、grant JSON、policy/subject revision、content digest、effective/expiry 和状态；具体 Skill package 数据仍归 E6。
4. 继续使用 E2 `roles`/`role_bindings`；E3 只写 `system/global` binding，角色权限映射必须有版本化 policy revision。
5. 复用 E2 append-only `audit_events`；对 grant、role、auth 和 recovery action 补齐 action-specific 必填字段校验。
6. 新增一条线性 Alembic revision，启动只校验精确 head，不自动 DDL；目标数据库必须为空或通过显式批准的 E3 migration guard。

### 4.2 密码合同

- 新增固定版本的 Argon2id 依赖并更新 lockfile。
- 离线兼容当前 Django 产生的 `pbkdf2_sha256` 及计划中明确列出的其他现有格式；FastAPI 不依赖 Django runtime。
- 成功验证旧 hash 后，在同一个用户写事务内升级 Argon2id；未知格式、损坏 hash 或参数越界拒绝。
- 密码输入只在内存中处理；审计只写结果、错误码和 correlation，不写密码或完整 hash。

### 4.3 认证状态机

```text
register -> active user -> session + access JWT + refresh cookie
login    -> active user + current token_version -> session + token pair
refresh  -> active session + active opaque token -> consume parent -> issue child
logout   -> revoke current session/family -> clear cookie
replay   -> reject parent -> revoke entire family -> audit impact
password change -> increment user token_version -> revoke all sessions -> issue new session
session revoke -> revoke one session/family -> reject new runs using that session
disabled/locked/expired/revision drift -> fail-closed
```

所有状态转换必须在 SQL transaction 内完成；外部 Redis、文件、Django API 或前端状态不得决定提交成功。

## 5. API 与前端合同

公开路径保持当前前端使用的 trailing-slash 路径：

| 路径 | 方法 | 认证 | 结果 |
|---|---|---|---|
| `/user/register/` | POST | 匿名 | 创建 active 用户、返回 access `token`、设置 refresh cookie |
| `/user/login/` | POST | 匿名 | username/email 唯一匹配后返回 access `token`、设置 refresh cookie |
| `/user/refresh-token/` | POST | refresh cookie | 原子轮换 opaque token，返回新 access `token` |
| `/user/logout/` | POST | access 或 refresh cookie | 撤销当前 session/family、清理 cookie |
| `/user/detail/` | GET | access | 返回当前用户和 profile |
| `/user/update/` | PUT | access | 更新 profile；非密码字段不改变其他 session |
| `/user/reset-password/` | POST | access | 校验旧密码，递增 token version，返回新 access `token` 并设置新 refresh cookie |
| `/user/sessions/` | GET | access | 返回当前用户 session 摘要 |
| `/user/sessions/{session_id}/revoke/` | POST | access | 当前用户撤销自己的指定 session |
| 管理撤销/审计路径 | POST/GET | `security_admin` | 以 SQL role binding 和 audit 决策为准 |

兼容原则：保留主要成功字段和路径；refresh 原文不再返回 JSON；错误响应改为稳定 code，不以旧中文文本作为客户端合同。Vite proxy、Axios refresh single-flight、`withCredentials` 和登录/注册页面必须同步更新。

## 6. 迁移、shadow、切换与回滚

### 6.1 迁移顺序

1. 执行口令通过后，创建 E3 隔离拓扑并运行 source/target/restore preflight；失败立即停止。
2. 对用户提供的只读 dump 生成 manifest、source digest、表结构和 PII 脱敏 inventory；不将 dump 或完整 hash 写入仓库。
3. 在空 E3 target 执行 dry-run：映射用户 UUID、规范化 email/phone、状态、hash、profile 和 `migration_maps`；发现关键冲突则整批拒绝。
4. 备份 E3 target，导入用户/profile/role bootstrap 前置数据；所有导入写入 correlation/audit。
5. 在独立 restore 库执行 bundle restore-forward，并对表结构、行数、canonical digest、约束和 migration map 对账。

### 6.2 Shadow 标准

- 对 dump 中全部用户完成标识、状态和 hash 校验；不能用随机小样本替代。
- 对已知凭据 fixture 完成 login、refresh、logout、replay、session revoke、password change、disabled/locked 全生命周期。
- 不向 Django 在线 login 端点发送会改变 `last_login` 的 POST；shadow 使用离线 verifier/read-only adapter 和明确的 fixture。
- 关键 mismatch 必须为零；任何不一致、缺字段、未知 revision 或 digest 漂移保持 `阻塞`。

### 6.3 切换和回退

- 切换前失败：不切 Vite proxy，Django 保持原活动路径；E3 target 只读保留现场。
- 切换后失败：停止 FastAPI 认证写入，恢复最近验证的 FastAPI snapshot；Django 只能作为只读/shadow adapter，不恢复双写。
- 无健康 snapshot、无法证明唯一写权威或回滚对账不一致时，保持 `阻塞`，不删除旧输入。
- 所有 rollback 采用停写、保留日志和 snapshot、restore-forward、结构/行数/digest/revision/audit 对账；populated 数据库不运行破坏性 downgrade。

## 7. 实施任务清单

- [ ] `E3-00`：执行口令校验、计划快照、资源 allowlist 和 E3 preflight；未收到 `开始执行e3` 时必须保持未执行。
- [ ] `E3-01`：建立 E3 隔离 MySQL source/restore 拓扑；保留 E1/E2 资源，不复用、不清理。
- [ ] `E3-02`：实现 `user_profiles`、session metadata、authorization grant schema 和 Alembic head gate。
- [ ] `E3-03`：实现 PBKDF2 兼容 verifier、Argon2id upgrade、FastAPI access JWT 和 opaque refresh rotation。
- [ ] `E3-04`：实现 MySQL auth repository/UoW：register、login、session、refresh、logout、revoke、password change；禁止 repository 自行越过 UoW commit。
- [ ] `E3-05`：实现用户只读迁移、全量 dry-run、UUID mapping、冲突报告、profile 导入和 restore-forward 对账。
- [ ] `E3-06`：实现 role binding、四眼 grant approve/revoke、system bootstrap CLI、统一授权决策和 current Skill/Tool/MCP 管理入口接入。
- [ ] `E3-07`：实现 append-only auth/role/grant/recovery audit、action-specific 必填字段、correlation 查询和稳定错误 code。
- [ ] `E3-08`：把 Vite `/user` proxy、Axios cookie、refresh single-flight、登录/注册/资料页面切到 FastAPI；删除旧 refresh localStorage 状态。
- [ ] `E3-09`：移除 YAML/环境变量管理员读取后门；确认没有 debug bypass、用户名推断或 Django/Redis 放行路径。
- [ ] `E3-10`：执行 shadow、切换、failure injection、回滚和浏览器/API 验收；实现完成后只标 `待验证`。
- [ ] `E3-11`：提交三份记录和全部证据给用户；用户明确验收后才将 E3 标为 `已关闭`。

## 8. 风险、保护和停止条件

- 误连当前业务库：任何未列入 E3 allowlist 的 host/port/database/DSN 立即停止；不读取 `.env` 作为隐式目标。
- 旧 Django/Redis 双权威：切换窗口不双写；Redis 丢失不得放行；Django 仅 read-only/shadow。
- token 泄漏：只存 opaque digest，access/refresh/cookie 不进日志、证据或审计 JSON。
- 迁移冲突：整批 dry-run fail-closed；不自动合并、不覆盖、不删除 source dump。
- 审批绕过：同人准备/批准、越权撤销、未知 revision、过期 grant、policy/content digest 漂移和 worker restart 全部拒绝并审计。
- 调试后门：必须在验收前删除；若仍能通过 YAML/环境变量或旧 helper 获得管理员写权限，E3 立即标 `阻塞`。
- cookie 风险：开发档位不增加 CSRF/Origin 防护，但仍固定 `HttpOnly + SameSite=Strict + Path`；不得将此档位描述为生产安全配置。
- 任何 fail-open、审计缺字段、未知状态、回滚不可执行、关键证据缺失或 E1/E2 资源被触碰，立即停止并保留现场。

## 9. 退出条件

- [ ] E3 source dump manifest、全量用户 dry-run、mapping、profile 和冲突报告可复核，且不含未脱敏 PII/完整 hash。
- [ ] E3 target/restore 为批准的 MySQL 8.4 隔离资源；schema head、约束、行数、digest、migration map 和 restore-forward 对账零差异。
- [ ] 全部七个 `/user/*` 主要流程由 FastAPI 提供；Vite/Chromium 浏览器 smoke 通过；Django 不接受新写入。
- [ ] access JWT、opaque refresh、cookie、rotation、replay、session revoke、password global revoke、disabled/locked/expired fail-closed 全部通过。
- [ ] PBKDF2 兼容和 Argon2id upgrade 通过；未知 hash、坏 hash、重复用户和冲突输入拒绝。
- [ ] `skill_admin`/`security_admin` 角色分离、四眼审批、grant approve/revoke、bootstrap、越权和 debug bypass 删除测试通过。
- [ ] API、前端、认证 repository、恢复和审计可按 correlation ID 对账；审计字段完整且无 secret/PII 泄漏。
- [ ] failure injection、FastAPI snapshot restore-forward、无双写回退和浏览器重试行为通过。
- [ ] 所有代码/配置/schema/前端变更均记录在 `change-log.md`；所有测试和限制均记录在 `test-record.md`。
- [ ] 实现者只能提交 `待验证`；用户完成第二次大确认后才允许 `已关闭`。

## 10. 回滚方案

1. 停止 FastAPI auth 写入、E3 runner 和所有 E3 导入；保留日志、correlation、preflight、revision、job/attempt、audit 和目标容器。
2. 校验最近 E3 bundle manifest、source digest、target server UUID 和 approval/preflight 指纹。
3. 将 snapshot restore 到新的 E3 restore 目标，不覆盖故障源库；执行 schema、行数、digest、FK/唯一约束、migration map、role、session 和 audit 对账。
4. 切换前失败时不改变 Django 活动路径；切换后失败时 Django 只保留 read-only/shadow，不能恢复双写。
5. 由用户决定 restore-forward、修复后重试或保持阻塞；任何资源删除、旧输入处置或 E3/E2 清理另行授权。

## 11. 未完成与明确不做

- 本文件创建前沿用的 Django/Redis 认证路径尚未改变。
- 未连接任何真实 Django/MySQL/Redis/Storage/Chroma，未读取任何 `.env`，未创建 E3 容器。
- 未执行 Alembic、用户 dump/import、shadow、proxy 切换、认证切换、浏览器 E2E 或 failure injection。
- E4 业务 UUID/FK 和业务表迁移、E5 RAG、E6 Skill package 迁移、AR-6 依赖删除/生产恢复仍不属于本批。
- 具体资源 ID、数据库账号、source dump 路径、Argon2 参数、错误 code 清单和 API schema 在执行口令通过后以本计划和 preflight 记录为准；不得在执行前擅自写入或猜测真实值。

## 12. 最终执行确认

当前状态：`待你确认`。  
在用户明确发出以下原文之前，所有 `E3-*` 任务均保持未执行：

```text
开始执行e3
```

收到该原文后，先执行 `E3-00` 计划/allowlist/preflight 复核，再按本清单实施；不会因为已有 E2 代码或局部 auth primitive 而跳过 E3 入口。  
实现和证据完成后，本批转为 `待验证`，等待用户第二次确认关闭。
