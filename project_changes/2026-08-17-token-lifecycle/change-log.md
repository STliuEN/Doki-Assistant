# 工作包 3 变更记录

日期：2026-08-17

- 重构 `DjangoUserService/apps/user/authentications.py`，新增 access/refresh token 对、issuer/audience 校验、共享 session ID、独立 JTI、token version、刷新轮换和重放拒绝。
- 更新 Django 登录、注册、刷新、密码重置、资料更新与注销流程，使签发接口返回 token 对，注销撤销两类凭据，撤销服务不可用时返回 `503`。
- 为 `User` 增加 `token_version`，并提交 `0002_user_token_version.py`；密码重置时递增版本以使旧 token 失效。
- 更新 FastAPI JWT 校验，要求 access token 类型及完整必需 claim，使用 `JWT_REDIS_URL` 对应的独立 Redis 连接，以确定性键同时兼容 Django cache key version，不再扫描 Redis keyspace。
- FastAPI 对黑名单存储故障采用 fail closed，并使用异步 `httpx` 调用 Django 用户服务；短 TTL 成功缓存降低每次请求复核用户状态的开销。
- 新增由 Django PyJWT 生成、供 Django 与 FastAPI 共同读取的 access token 合同 fixture，固定跨服务 claim 与算法兼容性。
- 统一前端认证状态到 `useUserStore`，持久化 access/refresh token；登录、注册和资料更新同步保存 token 对，注销请求携带 refresh token。
- Axios 响应拦截器新增单次自动刷新、并发刷新合并和失败清理；显式注销、刷新失败与无 refresh token 的 `401` 均清除 token、用户资料和登录标志。
- 新增 Django token 生命周期与真实 API 流程测试、跨服务 JWT 合同测试、FastAPI JWT 校验测试以及前端认证 store 测试。
- 2026-08-18 最终审计补强：Django 与 FastAPI 都把 `user_id/token_type/iss/aud/jti/sid/ver/iat/nbf/exp` 作为必需声明，拒绝空字符串、缺失时间声明和非法 token version；现有负向用例逐项删除声明验证拒绝行为。

兼容性说明：升级后旧的无类型 JWT 不再有效，客户端需要重新登录。登录和注册响应保留原 `token` 字段，并新增 `refresh_token` 与对应过期时间字段。
