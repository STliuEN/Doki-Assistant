# E1 API/UI/Prompt/route Characterization 矩阵

状态：已关闭

本矩阵记录当前代码和 E1 隔离/替身环境的可观察合同。`verified-live` 仅表示隔离真实依赖或本地浏览器确实运行；fixture/mock 仍使用 `verified-local`，不外推到生产。

| ID | 表面 | 输入/拓扑 | 期望合同 | 实际观察/证据 | 状态与限制 |
|---|---|---|---|---|---|
| API-01 | `GET /health/live`、`GET /health/ready` | FastAPI health router；Chroma 可为 ready/degraded | live 返回 envelope；ready 区分核心依赖与 Chroma projection 状态 | `health.py` 保留 `ready/degraded` 字段；Chroma API containment 与 probe 覆盖降级结构 | verified-local；真实目标 schema 的完整 lifespan/E2E 移交 E2 |
| API-02 | Chroma 相关 Knowledge routes | TestClient + `ChromaProjectionUnavailable` 替身 | HTTP 503，`{"code":503,"message":"Chroma projection is unavailable; retry after recovery","data":null}` | 单/多文件、stream、清理、MD5、embedding switch、detail/chunks 等 13 条路径通过 | verified-local；异常来自替身，不是 live HTTP server |
| API-03 | `POST /chat/rag/query` | TestClient + RAG service unavailable 替身 | 同一 503 envelope | `tests/test_chroma_http_containment.py` 通过；OpenAPI 含 503 | verified-local |
| API-04 | `GET /knowledge/list` | Chroma 不可用，source-only service | SQL/source list 仍可返回 200，不把 projection 故障扩大为所有读操作 | 空文档列表返回 200；OpenAPI 未声明 Chroma 503 | verified-local；不证明真实 DB 可用 |
| API-05 | Skill registry stale | SQLite/mock registry | stale revision 统一 503，不 ack 未完成事件 | 既有 Skill registry error/API suite 通过 | verified-local；统一 SQL 权威属于 AR-1/AR-2 |
| API-06 | 高风险确认 `POST /chat/agent/confirm` | 过期、已消费、越权或 revision 不匹配 pending action | 统一 410，要求重新发起；有效确认才进入 SSE | `chat.py` 和 confirmation/tool guard tests 覆盖 | verified-local；未连接真实认证/审计 |
| API-07 | OpenAPI response declarations | 导出当前 `backend/openapi.json` | Chroma 依赖路径声明 503；普通 source list 不伪造 503 | `export_openapi.py --check` 与 containment OpenAPI assertions 通过 | verified-local |
| UI-01 | `/login`、`/register` | Vite `127.0.0.1:18080`，Firefox Playwright | 页面可加载，表单字段和导航可见 | login/register snapshot 和截图生成；无 JS error | verified-live（本地浏览器）；未使用 Chrome |
| UI-02 | 注册失败状态 | `POST /user/register/` 代理目标不存在 | 502 不被当作成功，显示“注册失败，请重试” | 网络记录为 502，页面显示错误 | verified-live；这是代理失败表征，不是注册成功证据 |
| UI-03 | `/skills` Skill 管理器 | Playwright mock `/skills` API | 侧栏、Skill 列表、编辑器、资源区域可渲染 | mock catalog 后 `SkillManager` 渲染；资源路径/大小/digest UI 可观察 | verified-local；mock API，不证明真实后端 |
| UI-04 | 前端静态回归 | Node 22.20.0/npm 10.9.3（绝对 `node.exe` 入口） | tests/lint/build 全通过 | Vitest `6 files, 28 passed`；ESLint 和 production build 通过 | verified-local |
| PROMPT-01 | `prepare_agent_run` Skill 选择 | offline snapshot 或隔离 DB；显式 unknown/private/disabled Skill | 在 embedding/LLM 前以 400 拒绝；允许集限制路由 | `agent_run_service.py` 显式校验及 Skill authorization tests 通过 | verified-local；offline caller 不触碰 DB |
| PROMPT-02 | Tool 上界与 Prompt 注入文本 | 确定性 model script；`skill_ids`/`tool_ids` | system prompt 只列当前工具；未列出的能力不可用；高风险工具等待确认 | tool guard、chat stream 和 benchmark schema 覆盖 | verified-local；不证明真实模型服从度 |
| PROMPT-03 | 运行预算 | 长 Skill/prompt fixture | 最多 32 Skills、64 KiB Skill instructions、128 KiB system prompt | 常量和边界测试存在，离线回归可执行 | verified-local |
| PROMPT-04 | benchmark Skill/Tool 合同 | 显式工具与其最小授权 Skill fixture；`delete_memory` 绑定 `memory_cleanup` | 若 Skill 未授权 Tool 应稳定拒绝；fixture 必须显式声明授权且不得放宽生产合同 | 历史 smoke `3/4`、regression `78/117` 保留；修复后隔离 smoke `4/4`、regression `117/117`，平均分 `1.0`、零 error/硬 veto | verified-local；生产 `resolve_skills` 合同测试通过，不证明真实模型质量 |
| ROUTE-01 | Knowledge stream/config mutation | Chroma preflight dependency 在 response/写入前运行 | projection 不可用时不启动流、不写配置，直接 503 | stream 和 embedding switch route 增加 preflight；定向测试通过 | verified-local |
| ROUTE-02 | Agent SSE | `POST /chat/agent/query/stream` + deterministic stream | 首帧/终止事件遵循 SSE schema；registry stale 返回 503 | chat stream contract tests 和前端 SSE 客户端测试通过 | verified-local；完整真实模型未跑 |
| ROUTE-03 | 应用启动 schema gate | 主应用 schema gate + 隔离 pytest | 只读校验 revision `20260824_0002`，不自动 migration；纯 CORS 合同不启动 lifespan | 历史 `280 passed, 1 failed` 和无效 `282 passed` 保留；测试边界修复后最终隔离 pytest `284 passed`，受保护资源未变化 | verified-local；真实目标 schema 启动移交 E2，E1 未执行 migration |
| ROUTE-04 | 认证/业务真实 E2E | Vite proxy + 真实 Django/FastAPI/MySQL | 登录、注册、刷新、注销和业务写入可对账 | E1 只完成页面/代理失败表征；未连接现有业务服务 | not-run；不得用 mock 替代真实授权证据 |

## 解释规则

- `verified-live` 只覆盖 E1 专用容器、E1 专用 Chroma 目录或本地浏览器；不包含现有业务数据。
- `verified-local` 可以是代码、TestClient、SQLite、确定性 Embedding、mock 或离线 benchmark；它只能证明合同和隔离逻辑。
- `blocked` 表示有可复现失败且当前阶段明确禁止采取会改变权威数据的修复动作。
- `not-run` 表示环境未提供或不属于 E1，不得从缺少失败推断为通过。
- E1 范围内没有剩余 `blocked` 项；`ROUTE-04` 明确移交 E2，且 E1 关闭不授权自动启动 E2。
