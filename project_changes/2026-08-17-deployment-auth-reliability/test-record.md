# 工作包 4 测试记录

日期：2026-08-17
状态：完成

## 专项覆盖

- Django 生产配置拒绝弱 JWT 密钥、开启 DEBUG、空 allowed hosts、空 CORS allowlist 和缺失 `REDIS_CACHE_URL`；未知 `ENV` 同样拒绝启动。
- `seed_dev_user` 在隔离数据库中可幂等创建或更新账号，并在生产环境拒绝执行；默认应用启动不创建固定账号或执行 migration。
- Django 登录、注册和 refresh 使用独立限流 scope，计数存储故障返回 `503`。
- FastAPI 生产配置拒绝未知 `ENV`、`DEBUG_MODE=true`、占位或复用密钥、缺失 `JWT_REDIS_URL`、空或通配 CORS origin；固定窗口限流只执行一个带 TTL 的 Lua 脚本，超限返回 `429`。
- FastAPI lifespan、撤销状态 fail closed 和数据库 revision 启动校验均有合同测试。

## 最终发布门禁

| 检查 | 结果 |
|------|------|
| Backend pytest | `118 passed` |
| Backend Ruff | 通过 |
| Django system check | 通过 |
| Django migration drift | `No changes detected` |
| Django tests | SQLite + `LocMemCache` 下 `19 passed` |
| Frontend | `20 passed`，lint 与构建通过 |
| FastAPI OpenAPI | current |
| Alembic | `20260817_0001 (head)`，offline SQL 通过 |
| Offline Benchmark | smoke `4/4`；regression `117/117`，hard veto `0` |

## 隔离浏览器验收

临时 SQLite 环境中的注册、资料读取和注销分别返回 `201`、`200`、`200`。注销后认证持久化状态被完整清理；桌面和 `390x844` 移动视口无重叠，最终浏览器控制台 0 error、0 warning。截图保存在忽略目录 `output/playwright/auth-login-after-logout.png` 和 `output/playwright/auth-login-mobile.png`。

FastAPI 未在该浏览器流程中启动，笔记页的预期 `502` 不作为业务 API 通过证据。测试没有触碰现有 MySQL，临时数据库和服务已清理。

## 结论

启动副作用、生产 fail-fast、CORS、限流、撤销存储故障和浏览器认证主流程均已覆盖。生产部署必须显式提供环境专属密钥、host/origin allowlist 和 Redis 配置。
