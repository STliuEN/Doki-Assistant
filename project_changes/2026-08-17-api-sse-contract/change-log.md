# 工作包 6 变更记录

日期：2026-08-17
状态：完成

## API 合同

- 新增 `backend/app/schemas/api.py`，定义泛型 `ApiResponse[T]`。
- 更新 `success_response` 返回验证后的 `ApiResponse`，不再通过手工 `JSONResponse` 绕开 response model。
- 为 canonical JSON handler 声明对应的 `ApiResponse[T]`，使 OpenAPI 与真实 `{code,message,data}` 响应一致。
- 保留文件下载和流式响应的专用 response 类型，不错误套用 JSON envelope。
- 重新生成 `backend/openapi.json`，并通过生成物漂移检查。

## SSE 合同

- 新增 `backend/app/schemas/sse.py`，集中定义 `SSE_SCHEMA_VERSION = "1.0"`、OpenAPI `text/event-stream` 描述和事件编码。
- chat query/regenerate/confirm、knowledge ingestion、note polishing 和 realtime translate 的 SSE data frame 统一携带 `schema_version`。
- SSE 路由在 OpenAPI 明确发布 `text/event-stream`，客户端不再需要从未声明的响应体猜测流格式。
- 删除知识上传 SSE 的路由级 `Access-Control-Allow-Origin: *`，所有普通与流式响应统一由应用 CORS allowlist 中间件决定 origin。

## 特征测试与文档

- 新增真实 FastAPI 响应和 OpenAPI 扫描测试，确保调用 `success_response` 的 JSON handler 发布 envelope schema。
- 扩充 chat stream 合同测试，验证正常、错误和终止事件都携带稳定版本。
- 补齐跨服务 access token、Django 认证生命周期、限流、迁移和生产配置边界测试。
- 更新 Django Swagger/API 文档，说明 access/refresh token、轮换、注销和撤销存储故障 `503` 合同。
- 通过隔离 Playwright 流程验证注册、资料读取、注销与持久化状态清理；测试未连接现有 MySQL。

兼容性说明：现有 JSON envelope 不变，OpenAPI 现在准确描述它；SSE 新增版本字段。依赖旧的裸 JSON OpenAPI 类型生成客户端需要重新生成类型并复核。
