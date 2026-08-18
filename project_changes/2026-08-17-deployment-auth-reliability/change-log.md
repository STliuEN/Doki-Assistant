# 工作包 4 变更记录

日期：2026-08-17

- 精简 `DjangoUserService/apps/user/apps.py`，删除启动线程、自动建库、`makemigrations`、`migrate` 和 `admin/admin1234` 创建逻辑。
- 新增 `seed_dev_user` 管理命令，要求显式传入密码，并在生产环境拒绝运行；前端登录页同步移除测试账号自动填充入口。
- 收紧 Django 配置：生产环境检查强密钥、DEBUG、allowed hosts、CORS allowlist 和 Redis cache URL，恢复 CSRF middleware，并启用 secure cookie、`nosniff` 与 `X-Frame-Options: DENY`。
- 收紧 FastAPI 配置：只接受受支持的 `ENV`，生产要求 `DEBUG_MODE=false`，校验 JWT 与模型配置密钥的强度和分离、要求显式 `JWT_REDIS_URL`、强制认证状态复核，并拒绝缺失或通配的浏览器 origin；CORS 方法和请求头改为最小集合。
- 为 Django 登录、注册和 refresh 接口配置独立固定窗口限流；计数使用 cache `add`/`incr`，仅在 `TRUST_PROXY_HEADERS=true` 时信任转发 IP，缓存异常返回 `503`。
- FastAPI 全局与路由限流使用单个 Redis Lua 脚本原子创建/递增固定窗口计数并保证 TTL；生产默认启用，开发默认关闭，阈值可由环境变量配置。
- FastAPI 启动与清理由 `lifespan` 统一管理；启动时执行安全配置和 Alembic revision 验证，不再自动创建表或补列。
- CI 增加 Django system check、migration drift 和 test 门禁；数据库相关验证使用临时 SQLite 或 Alembic offline SQL，不访问现有 MySQL。
- 2026-08-18 最终审计补强：`prod` 与 `production` 使用同一安全分支，未知环境名拒绝启动；生产调试响应开启时 fail fast，防止异常路径和 traceback 返回客户端；知识上传 SSE 删除路由级通配 CORS 头。

兼容性说明：生产环境升级后必须补齐 host、origin、Redis 和密钥配置；未列入 allowlist 的浏览器来源将无法跨域访问。开发环境不再自动获得默认账号，需要显式执行开发账号命令或正常注册。
