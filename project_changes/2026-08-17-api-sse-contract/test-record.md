# 工作包 6 测试记录

日期：2026-08-17
状态：完成

## API 与 SSE 专项合同

- `success_response` 返回 `ApiResponse` 模型实例，并能验证嵌套 Pydantic 数据。
- 真实 ASGI 请求返回 `{code,message,data}`，OpenAPI 对同一路由引用 `ApiResponse` schema。
- 路由扫描确认所有 canonical JSON handler 都声明 envelope；文件与 SSE 使用各自媒体类型。
- 所有 SSE 路由在 OpenAPI 发布 `text/event-stream` 示例。
- SSE 路由源码扫描确认不再写入路由级 `Access-Control-Allow-Origin`，避免覆盖应用 allowlist。
- SSE encoder 会覆盖调用方伪造的版本值，正常事件、错误事件和终止事件均固定为 `schema_version: "1.0"`。
- Django 与 FastAPI 读取同一 `contracts/auth_access_token.json` 样本，验证 issuer、audience、token type、JTI 和算法兼容性。

## 最终自动化门禁

| 检查 | 结果 |
|------|------|
| Backend pytest | `118 passed` |
| Backend Ruff | 通过 |
| Django system check | 通过 |
| Django migration drift | `No changes detected` |
| Django tests | SQLite + `LocMemCache` 下 `19 passed` |
| Frontend tests | `20 passed` |
| Frontend lint | 通过，0 warning |
| Frontend build | `dist-build-check` 构建通过 |
| FastAPI OpenAPI | `scripts/export_openapi.py --check` 通过，生成物 current |
| Alembic | `20260817_0001 (head)`；offline SQL 通过 |
| Lock / requirements | backend、Django `uv lock --check` 与导出产物检查通过 |
| Offline smoke benchmark | `4/4` |
| Offline regression benchmark | `117/117`，hard veto `0` |

## 浏览器验收

在临时 SQLite 和 `LocMemCache` 环境完成真实浏览器流程：

| 步骤 | 结果 |
|------|------|
| 注册 | HTTP `201` |
| 读取资料 | HTTP `200` |
| 注销 | HTTP `200` |
| 注销后状态 | access token、refresh token、userInfo 全部清空 |
| 视口 | 桌面与 `390x844` 移动端无重叠 |
| 最终控制台 | 0 error、0 warning |

验收截图保存在忽略目录 `output/playwright/auth-login-after-logout.png` 与 `output/playwright/auth-login-mobile.png`。浏览器验收未启动 FastAPI，因此笔记页请求的预期 `502` 不计入 API 合同通过项；所有临时数据库、服务和浏览器进程均已关闭。

## 安全边界与结论

首次 requirements 检查发现新增 Alembic 后的 backend 导出产物漂移；重新生成 backend 与 Django requirements 后，`scripts/export-requirements.ps1 -Check` 通过。该中途发现已闭环，不作为遗留阻塞。

测试只使用临时 SQLite、`LocMemCache`、Alembic offline SQL 和离线 benchmark，没有连接或修改现有 MySQL。API envelope、SSE 版本、认证与迁移合同均已成为可重复执行的发布门禁，工作包 6 完成。
