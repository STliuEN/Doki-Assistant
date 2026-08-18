# 工作包 4：部署与认证可靠性

日期：2026-08-17
状态：已完成（最终复核：2026-08-18）
关联记录：同目录 `change-log.md`、`test-record.md`

## 目标

移除 Web 进程启动时的数据库和测试账号副作用，使开发与生产配置边界可验证、错误配置尽早失败，并为浏览器跨域、认证入口和全局 API 提供明确的限流策略。

## 实施范围

- Django 应用加载时不再创建数据库、生成或执行 migration，也不再自动创建固定测试账号；开发账号仅能通过显式管理命令创建。
- 删除登录页中的固定测试账号填充入口，避免默认凭据进入正常用户流程。
- Django 生产环境强制使用非占位强密钥、关闭 DEBUG、配置 allowed hosts、显式 CORS allowlist 与 Redis token 撤销存储，并启用安全 cookie、内容嗅探和 frame 限制。
- FastAPI 生产环境校验 JWT 密钥、模型配置加密密钥、JWT 撤销存储、认证状态复核开关和 CORS allowlist，并拒绝通配 origin；CORS 仅开放应用使用的方法和请求头，未知 `ENV` 或生产调试响应会 fail fast。
- Django 登录、注册和 refresh 接口按独立 scope 限流；代理头仅在显式信任时参与客户端 IP 识别，计数存储故障返回 `503`。
- FastAPI 限流在生产环境默认启用、开发环境默认关闭，使用单个 Redis Lua 脚本原子创建/递增固定窗口计数并保证 TTL，并允许通过环境变量调整全局阈值。
- FastAPI 使用 lifespan 统一初始化和释放数据库会话、Redis、后台资源与连接池；数据库启动步骤只验证 Alembic revision，不自动修改 schema。

## 部署边界

- 本工作包不连接、不读取、不写入现有用户 MySQL；数据库初始化、升级和现有库接管遵循工作包 5 的显式 migration 流程。
- `seed_dev_user --password ...` 只用于明确选择的非生产环境，并在 `ENV=prod` 或 `ENV=production` 时拒绝执行。
- 生产部署必须提供环境专属密钥、host/origin allowlist、Django `REDIS_CACHE_URL` 和 FastAPI `JWT_REDIS_URL`；缺失配置将阻止服务启动或认证继续运行。
- 新的限流和 fail-closed 行为会新增合法的 `429` 与 `503` 响应，调用方需要按状态码退避或重试，不能将其当作认证成功。

## 回滚方式

可按组件回滚 allowlist、限流中间件或配置校验，但不得恢复启动期自动迁移、默认测试账号和生产通配 CORS。若回滚影响认证 Redis、密钥或 token 配置，应先停止流量并确认前后端共享配置一致，再恢复服务。
