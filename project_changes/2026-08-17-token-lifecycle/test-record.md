# 工作包 3 测试记录

日期：2026-08-17
状态：完成

## 专项覆盖

- Django：跨服务合同样本、access/refresh 声明、过期 refresh、token 类型冒用、原子轮换、重放拒绝、密码重置后的 token version 失效、停用用户、注销后访问拒绝，以及撤销存储故障返回 `503`。
- FastAPI：读取同一合同样本，只接受具有完整必需声明的 access JWT；逐项缺少 `token_type/jti/sid/ver/iat/nbf/exp` 均被拒绝，并验证确定性撤销键、已撤销 token 返回 `401`、撤销存储故障返回 `503`。
- Frontend：access/refresh token 在同一个 Zustand 持久化 store 中管理；并发 `401` 只触发一次刷新；轮换保留用户资料；刷新失败、显式注销和缺少 refresh token 时完整清理认证状态。

## 最终发布门禁

```text
backend> uv run --frozen pytest -p no:cacheprovider
118 passed

backend> uv run --frozen ruff check main.py app tests scripts
passed

DjangoUserService> ENV=test + SQLite + LocMemCache
system check passed
No changes detected
19 tests passed

front> npm test
20 passed

front> npm run lint -- --max-warnings 0
passed

front> npm run build -- --outDir dist-build-check
passed
```

FastAPI OpenAPI 漂移检查通过；Alembic head 为 `20260817_0001` 且 offline SQL 生成通过；离线 smoke benchmark 为 `4/4`，完整 regression benchmark 为 `117/117`，hard veto 为 `0`。

## 隔离浏览器主流程

使用临时 SQLite 数据库和测试环境 `LocMemCache` 完成真实浏览器认证流程：注册返回 `201`、资料读取返回 `200`、注销返回 `200`；注销后 Zustand 中 access token、refresh token 和用户资料均为空。桌面与 `390x844` 移动视口未发现重叠，最终控制台为 0 error、0 warning。

本轮未启动 FastAPI，因此笔记页业务请求出现预期 `502`；该结果不属于认证失败，也没有连接或修改现有 FastAPI/MySQL 数据。临时 SQLite、测试服务和浏览器进程均已清理。

## 结论

access/refresh 类型边界、刷新轮换、撤销、用户状态复核和前端失败清理均有自动化或浏览器证据。旧的无类型 JWT 不再受支持，升级后用户必须重新登录。
