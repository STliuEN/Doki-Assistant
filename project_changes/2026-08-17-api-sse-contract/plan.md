# 工作包 6：API 与 SSE 合同及特征测试

日期：2026-08-17
状态：已完成（最终复核：2026-08-18）
关联记录：同目录 `change-log.md`、`test-record.md`

## 目标

使 FastAPI 的真实 JSON 响应、OpenAPI 描述和 SSE 数据帧具有同一套可版本化合同，并把认证状态码、跨服务 token、迁移边界和关键浏览器认证流程纳入自动化验证。

## 实施范围

- 定义泛型 `ApiResponse[T]`，统一 canonical JSON 成功响应的 `{code,message,data}` envelope 及 OpenAPI schema。
- 让 `success_response` 返回经过 Pydantic 验证的模型实例，避免响应构造绕过 schema 校验。
- 区分普通 JSON、文件响应与 SSE；所有 SSE 路由在 OpenAPI 声明 `text/event-stream`。
- 为 chat、knowledge、note 和 translate 的每个 SSE data frame 固定写入 `schema_version: "1.0"`，客户端可按版本选择解析策略。
- 移除知识上传 SSE 路由级通配 CORS 头，普通响应和流式响应统一由应用 allowlist 中间件处理。
- 增加真实 ASGI 响应、OpenAPI 路由扫描、SSE 编码与流式终止合同测试。
- 补齐 Django 真实认证流程、Django/FastAPI 共享 JWT 样本、撤销存储故障、限流和数据库 revision 特征测试。
- 使用隔离浏览器环境验证注册、资料读取、注销、认证持久化清理和桌面/移动布局。

## 兼容性边界

- JSON 成功响应继续使用现有 `{code,message,data}` 结构；本工作包主要修正 OpenAPI 与运行时校验，不引入新的 envelope。
- SSE 消费者必须忽略未知字段；新增 `schema_version` 为向后兼容字段，后续不兼容变更必须提升版本并定义兼容窗口。
- 文件下载与 SSE 不强制套用 JSON envelope。
- 认证协议仍遵循工作包 3：旧的无类型 JWT 被拒绝，撤销状态无法确认时返回 `503`。

## 回滚方式

可以按路由回滚 response model 或 SSE schema helper，但必须同时回滚对应 OpenAPI 生成物和合同测试。不得只删除测试来保留运行时与文档漂移；若移除 `schema_version`，需先确认所有客户端均未依赖该字段。
