# 工作包 3：访问令牌与刷新令牌生命周期

日期：2026-08-17
状态：已完成（最终复核：2026-08-18）
关联记录：同目录 `change-log.md`、`test-record.md`

## 目标

将单一长时效 JWT 升级为可区分、可轮换、可撤销的 access/refresh token 对，统一 Django、FastAPI 与前端对登录状态的判断，并在撤销存储或用户状态服务不可用时拒绝继续放行认证请求。

## 实施范围

- Django 为 access token 和 refresh token 写入 `token_type`、`iss`、`aud`、`jti`、`sid`、`ver`、`iat`、`nbf` 与 `exp`，默认有效期分别为 15 分钟和 30 天。
- 登录、注册、密码重置和用户资料更新返回新的 token 对；刷新接口只接受 refresh token，并在签发新 token 对前原子消费旧 refresh token。
- access token 不得用于刷新，refresh token 不得用于业务接口；过期、已撤销、缺少必要声明、用户停用或 token version 失配的凭据均被拒绝。
- 注销同时撤销 access token 与 refresh token；撤销存储读写异常返回 `503`，不以“注销成功”或“认证成功”掩盖失败。
- FastAPI 使用独立的 JWT Redis 连接和确定性黑名单键检查撤销状态，不再执行 Redis `KEYS` 扫描；认证成功后通过短 TTL 缓存复核 Django 用户状态。
- 前端使用 Zustand 持久化存储统一管理 access token、refresh token、用户资料和登录标志；响应拦截器只重试一次，并合并并发刷新请求。

## 兼容性与安全边界

- 旧 JWT 缺少 `token_type`、`jti`、issuer 或 audience 时会被拒绝，升级后用户需要重新登录。
- 前端可读取旧的 `jwt_token` 作为一次性兼容入口，但旧状态不包含 refresh token，首次 `401` 后会清理认证状态并返回登录页。
- FastAPI 对 Redis 黑名单检查、短期用户状态缓存或 Django 用户服务异常采用 fail closed；用户可能暂时收到 `503`，但不会在无法确认撤销状态时继续访问。
- `User.token_version` 用于批量失效旧凭据；字段的版本化数据库交付由工作包 5 管理。

## 回滚方式

代码回滚不能恢复已经撤销或已经轮换的 refresh token。若必须回退到旧认证协议，应先停止签发新 token 对，明确前后端兼容窗口，再回滚服务并强制所有用户重新登录；不得重新接受缺少类型和唯一标识的历史 JWT。
