# 安全与可靠性加固计划

状态：待实施
审查日期：2026-07-16
最近复核：2026-08-17
适用范围：当前 `ai_document_assistant` 分支

本文记录全仓审查确认的安全、认证、数据库演进和接口合同问题。这里是整改细节的唯一事实来源；[改进执行选择](./improvement_execution_plan.md) 提供可按序号启动的工作包，[全量重构开发计划](./roadmap_next.md) 只维护阶段和依赖，[开发与运行说明](./development_setup.md) 只维护操作和部署边界。

在本文的 P0/P1 项完成并通过验收前，项目只按受信任机器上的本地开发应用使用，不应直接暴露到公网，也不应向不受信任用户开放账号。

## 已验证基线

审查时得到以下结果：

| 检查 | 结果 |
|------|------|
| Backend pytest | 82 passed |
| Backend CI 范围 Ruff | passed |
| Backend 全仓 Ruff | 7 个问题，位于 `mcp_servers/` 和 `seed_templates.py` |
| Frontend lint | passed |
| Frontend Vitest | 4 passed |
| Frontend TypeScript/build | passed |
| Django system check | passed |
| Django tests | 0 tests |
| OpenAPI/requirements/lock 漂移 | passed |
| 文档检查 | 2026-08-17 复核：117 个 Markdown、73 个本地链接通过 |
| Offline Benchmark | 2026-08-17 复核：smoke 4/4、regression 117/117 |

通过现有检查不表示已经覆盖本文问题。当前测试集中在 Agent 运行时、Benchmark 和聊天 SSE；知识库路径、JWT 生命周期、Django 用户流程和服务端网络出口仍缺少回归测试。

## 风险清单

| ID | 优先级 | 当前行为 | 影响 | 完成条件 |
|----|--------|----------|------|----------|
| SEC-01 | P0 | 知识库图片接口直接拼接 `md5` 和 `filename` | Windows 反斜杠可造成目录穿越、文件读取或目录枚举 | 所有文件访问统一做根目录约束，并覆盖编码路径测试 |
| SEC-02 | P0 | 聊天消息使用 `rehypeRaw` 渲染，未接入 HTML sanitizer | 模型或历史消息中的 HTML 可形成持久化前端注入面 | 默认禁用原始 HTML，或使用最小白名单净化并增加恶意输入测试 |
| AUTH-01 | P0 | refresh 解码时忽略 `exp`，且不校验用户 active/status | 旧 token 可被无限刷新，被锁定用户仍可能继续使用 FastAPI | 独立 refresh token、固定刷新期限、用户状态和 token version 校验 |
| AUTH-02 | P1 | FastAPI 每次认证用 Redis `KEYS` 搜索黑名单，Redis 失败时放行 | Redis 被阻塞；撤销检查不可用时旧 token 继续生效 | 使用确定键查询，明确 fail-open/fail-closed 策略并增加故障测试 |
| AUTH-03 | P1 | JWT 同时写入 `jwt_token` 和持久化 Zustand store，401 只删除前者 | token 残留且 `isLogin` 仍为真，形成认证状态分裂 | 只保留一个认证来源；401、注销和刷新失败原子清理完整认证状态 |
| DEPLOY-01 | P0 | 开发服务器自动创建固定凭据账号，UI 可一键填充 | 服务被意外暴露时产生已知账号 | 测试账号改为显式 seed 命令或 opt-in 环境变量，默认不创建 |
| DEPLOY-02 | P0 | Django 固定 DEBUG/宽松 CORS，FastAPI 允许任意 origin | 当前配置不具备公网边界 | production profile 强制 allowlist、强 secret 和安全 header |
| NET-01 | P1 | 用户可配置模型/Embedding `base_url`，后端直接发起请求 | 多用户部署时可访问内网、loopback 或 link-local 地址 | 定义 egress 策略；公网模式阻断私网地址或只允许管理员白名单 |
| DB-01 | P0 | Django migrations 被 Git 忽略并在运行时生成 | 干净环境、升级、多实例和回滚不可重复 | 跟踪 migration，CI 从空库应用完整序列 |
| DB-02 | P0 | FastAPI 使用 `create_all` 和自定义补列 | 不能可靠处理改列、删列、约束和回滚 | 引入 Alembic baseline，启动过程不再修改 schema |
| API-01 | P1 | 路由声明裸 `response_model`，实际返回 `{code,message,data}` | OpenAPI 与真实响应不一致，响应校验被绕过 | 定义泛型 envelope schema，并用 Pydantic/普通对象返回 |
| USER-01 | P1 | 用户名可重复，登录按用户名只取第一条 | 同名后注册用户可能无法通过 UI 登录 | 用户名唯一，或前后端统一使用唯一邮箱/用户 ID 登录 |
| REL-01 | P1 | FastAPI 异步鉴权路径调用同步 `requests.get` 且没有 timeout | Django 或网络异常会阻塞事件循环，造成请求堆积 | 使用共享异步 HTTP client，设置 connect/read/total timeout、取消和确定失败语义 |
| TEST-01 | P1 | Django 0 测试、前端仅 4 项，CI Ruff 未覆盖全仓 | 核心认证和文件边界缺少回归保护 | 增加分层测试并把 Ruff 范围扩展到所有维护代码 |
| UI-01 | P2 | 头像 UI 未连接上传；后端写入前不创建 `media/img` | 头像功能不是完整用户流程 | 完成选择、上传、目录创建、失败反馈和测试 |

## S0 文件系统边界

优先处理 `SEC-01`，完成前不要扩展知识库图片接口。

实施要求：

1. `md5` 只接受 32 位小写十六进制值；大小写兼容应先规范化再校验。
2. `filename` 必须等于其 basename，只允许已支持的图片后缀。
3. 使用一个共享 helper：拼接后 `resolve()`，再确认结果位于 `data/extracted_images/<user_id>/<md5>/` 内。
4. 读接口不得调用 `makedirs`；目录不存在直接返回 404。
5. 批量读取只读取允许的普通图片文件，并限制文件数和总返回字节数。
6. 删除目录使用同一个 containment helper，不能单独实现路径逻辑。

必需测试：

- 正常 MD5 和文件名。
- `..`、反斜杠、编码后的反斜杠、绝对路径和盘符。
- symlink/reparse point 边界；无法安全支持时显式拒绝。
- 其他用户目录、项目配置目录和不存在目录。
- 批量接口的数量、大小上限和非图片过滤。

## S1 前端内容与凭据

`SEC-02` 的默认方案是移除 `rehypeRaw`，继续使用 Markdown 语法。只有产品明确需要 HTML 时，才引入 `rehype-sanitize` 或等价 sanitizer，并维护最小允许标签/属性集合。

验收至少覆盖：

- `script`、事件属性、`iframe/srcdoc`、`object`、`javascript:` URL 和危险 data URL。
- 代码块、表格、链接和高亮等正常 Markdown 不回归。
- 流式中间态和历史消息使用同一渲染策略。

JWT 当前保存在 `localStorage`，且同时进入 `jwt_token` 和 Zustand persist 数据。短期必须先消除可执行 HTML，并让 Axios、SSE、路由守卫和用户 store 只读取一个认证来源；401、注销和 refresh 失败必须原子清理 token、用户信息和 `isLogin`。长期评估使用 `HttpOnly`、`Secure`、`SameSite` cookie，并同步解决 CSRF、SSE 和跨服务代理合同。

## S2 认证生命周期

访问 token 和 refresh token 应有不同的 `type`、有效期和使用端点。refresh 流程必须验证：

- 签名、issuer、audience、token type、`iat` 和最大刷新期限。
- 用户仍存在且处于 active 状态。
- token version/session version 未被用户注销、改密或管理员撤销。
- refresh token 轮换后旧 token 不可再次使用。

FastAPI 不能只从 payload 提取 `user_id` 后永久信任。可选方案是短 TTL 用户状态缓存加 token version，避免每个业务请求同步调用 Django。

Redis 黑名单使用可计算的完整键，禁止请求路径调用 `KEYS`。需要分别测试 Redis 正常、超时和不可用时的策略，并在文档中说明安全与可用性的取舍。

跨服务用户查询不得在 `async def` 中直接调用同步 `requests`。迁移 Django 前，使用共享 `httpx.AsyncClient` 或等价异步 client，设置 connect/read/write/pool timeout，传播取消，并把无响应、超时和无效响应映射为确定的认证或依赖服务错误；不能无限等待，也不能把所有失败静默降级为未命中。

## S3 部署与网络出口

测试账号只允许通过显式命令创建，例如 `manage.py seed_dev_user`；命令必须要求调用者传入密码，或生成一次性随机密码。前端不再内置固定凭据。

production profile 至少应满足：

- Django `DEBUG=False`，配置 `ALLOWED_HOSTS`、可信 CORS/CSRF origins。
- FastAPI CORS 使用明确 allowlist；不组合 wildcard origin 与 credentials。
- 两个服务拒绝空、示例或弱 secret。
- 登录、注册、refresh、模型测试和文件处理有独立限流。
- 配置安全 header、TLS 终止、代理信任边界和日志脱敏。

模型和 Embedding 自定义地址是产品能力，也是服务端 egress 能力。单机模式可显式允许 loopback；多用户/公网模式必须解析 DNS 后阻断 loopback、private、link-local、multicast 和云 metadata 地址，并防止重定向绕过。更稳妥的方案是仅管理员维护 provider allowlist。

## S4 数据库与 API 合同

Django：

- 从 `.gitignore` 移除通用 `migrations/` 规则，只忽略缓存文件。
- 提交当前 user baseline migration，不在 `AppConfig.ready()` 中运行 `makemigrations`/`migrate`。
- CI 在临时数据库执行 `migrate`、`makemigrations --check --dry-run` 和用户流程测试。

FastAPI：

- 为当前 metadata 生成并人工审阅 Alembic baseline。
- 用 migration 管理新增、修改、约束、索引和数据回填。
- 应用启动只检查 schema 版本，不执行通用 DDL。

API：

- 定义 `ApiResponse[T]`，让 OpenAPI 展示实际 envelope。
- 不用 `JSONResponse` 绕过成功响应校验；文件和 SSE 响应单独声明。
- 增加一项自动测试，对比 OpenAPI schema 与真实 TestClient 响应。

## S5 用户流程与测试

先确定登录主标识：如果 UI 叫“用户名”，数据库必须唯一；如果使用邮箱，前端字段、文案和请求体必须一致。数据库约束和 serializer 校验都要处理并发注册冲突。

头像流程需要连接文件 input、上传 API 和用户状态刷新，后端使用 Django storage API 保存文件，而不是直接 `open()` 路径。

建议的最小新增测试集：

| 层 | 必需覆盖 |
|----|----------|
| Backend unit/API | 路径 containment、SSRF 地址策略、response envelope、认证故障策略 |
| Django | 注册、重复用户名/邮箱、登录、锁定、refresh、注销、改密、头像上传 |
| Frontend | Markdown 安全渲染、单一认证来源、401/注销完整清理、登录、Profile 上传、主要 API 错误态 |
| Integration | Django 签发/撤销 token 后 FastAPI 的接受与拒绝行为；Django 超时、取消和无效响应 |
| Benchmark | 认证/隔离 hard veto、路径输入和危险 HTML 不进入可执行渲染 |

## 实施顺序

```text
SEC-01 filesystem containment
  -> SEC-02 safe message rendering
  -> AUTH-01/AUTH-02/AUTH-03 token lifecycle and client state
  -> DEPLOY-01/DEPLOY-02, NET-01 and REL-01
  -> DB-01/DB-02 migrations
  -> API-01 response contract
  -> USER-01/UI-01 product cleanup
  -> TEST-01 full gates
```

安全修复应使用独立、可回滚提交。每项提交同时包含对应测试和必要文档，不把目录穿越、认证重构、数据库 migration 和前端渲染改动压进同一个提交。

具体启动哪个工作包，以 [改进执行选择](./improvement_execution_plan.md) 的序号为准。

## 公网就绪条件

只有同时满足以下条件，才能把文档中的“仅本地开发”限制改为支持公网部署：

- P0 项全部关闭并有回归测试。
- production profile 和反向代理/TLS 流程经过干净环境演练。
- migration 可从空库执行，并对现有数据完成备份恢复演练。
- 任意用户输入不能突破文件根目录或服务端网络出口策略。
- token 锁定、改密、注销、过期和刷新在 Django/FastAPI 间一致。
- Django、前端和跨服务认证测试进入 CI required checks。
- 依赖漏洞扫描、secret scanning 和部署回滚清单已接入。
