# 改进执行计划

状态：工作包 `1-6` 已完成；工作包 `7-10` 保留、未执行

最近复核：2026-08-18

适用范围：当前 `ai_document_assistant` 分支

本文把 [全量重构开发计划](./roadmap_next.md) 和 [安全与可靠性加固计划](./security_hardening_plan.md) 转换为可独立执行、验收和回滚的工作包。`1-6` 已按依赖顺序完成，实施证据保存在 `project_changes/`；`7-10` 是下一轮可选择的产品与运维工作，不属于本轮交付。

## 当前验证基线

| 检查 | 2026-08-18 最终复跑结果 |
|------|--------------------|
| Backend pytest | `118 passed` |
| Backend Ruff | passed |
| FastAPI OpenAPI | current，生成文件检查通过 |
| Alembic | 单一 head `20260817_0001`；offline SQL 生成通过 |
| Django system check / migration drift | passed；`No changes detected` |
| Django tests | 隔离 SQLite 与 LocMemCache，`19 passed` |
| Frontend Vitest | `20 passed` |
| Frontend lint / build | passed |
| Offline Benchmark | smoke `4/4`；regression `117/117`，无 hard veto |
| 浏览器主流程 | Firefox 完成注册、资料读取、注销和移动端复核；控制台 0 error / 0 warning |

2026-08-18 复跑补记：后端全量测试、Ruff、OpenAPI、Alembic head/offline SQL、离线 smoke 和 regression 均再次通过；本次只使用离线/隔离验证，没有连接或修改现有 MySQL。

数据库相关验证只使用临时 SQLite、Alembic offline SQL 和 revision 检查，没有连接或修改现有 MySQL。浏览器验收未启动 FastAPI，因此没有读取业务 MySQL；笔记页请求出现预期的 `502`，不计为已覆盖的业务主流程。

## 本轮兼容性说明

- 认证升级为 access/refresh token 对，refresh token 轮换且拒绝重放；旧的无类型 JWT 不再有效，升级后客户端必须重新登录。
- 前端认证状态统一由 Zustand store 管理；并发刷新去重，刷新失败、`401` 和注销都会完整清理认证状态。
- Django 与 FastAPI 启动都不再创建数据库、生成 migration、执行通用 DDL 或创建固定账号。
- 生产配置现在要求受支持的 `ENV`、关闭调试响应、强密钥、明确 host/CORS allowlist 和 Redis 配置；未知、缺失或通配配置会在启动阶段失败。

## 工作包状态

| 序号 | 工作包 | 状态 | 已交付或保留范围 | 核心验收 |
|------|--------|------|------------------|----------|
| 1 | 知识库路径 containment | 已完成 | 统一安全路径 helper；校验 MD5、文件名、扩展名和根目录；逐级拒绝 symlink/junction；批量限制 100 个文件、25 MiB | 目录穿越、绝对/盘符路径、跨用户及根/用户/MD5/文件链接拒绝测试通过 |
| 2 | 聊天安全渲染 | 已完成 | 移除 `rehypeRaw`；流式和历史消息统一使用 `ChatMarkdown`；过滤危险 URL | XSS、事件属性、iframe 和危险协议测试通过，标准 Markdown 保持可用 |
| 3 | Token 生命周期与前端认证状态 | 已完成 | access/refresh token、严格 claim、轮换/重放拒绝、token version、确定性 Redis 撤销键、前端单一认证来源 | Django/FastAPI 共享合同、注销/刷新/Redis 故障及前端清理测试通过 |
| 4 | 部署与鉴权可靠性 | 已完成 | 移除固定账号和启动副作用；增加环境枚举、生产调试 fail-fast、CORS allowlist、原子限流和 FastAPI lifespan | 生产配置、异常脱敏、Lua 计数 TTL、异步鉴权及启动可靠性测试通过 |
| 5 | 版本化数据库迁移 | 已完成 | 跟踪 Django migration；Alembic baseline 含 ORM 唯一约束；启动只验证 revision，不修改 schema | Django drift、Alembic metadata/head/offline SQL 和 CI migration gate 通过；未触碰现有 MySQL |
| 6 | API/SSE 合同与特征测试 | 已完成 | 泛型 `ApiResponse[T]`；OpenAPI 发布实际 envelope；SSE 固定 `schema_version: "1.0"`；补齐真实响应和认证合同测试 | OpenAPI、真实响应、SSE、迁移、限流及浏览器认证主流程通过 |
| 7 | 回答引用与一键沉淀 | 保留，未执行 | SSE 返回文档、页码、chunk 和得分；前端来源抽屉；回答保存为笔记或记忆并保留来源 | 引用可回到原文；保存结果可追溯；越权来源不可见 |
| 8 | 知识处理任务中心 | 保留，未执行 | 持久化 queued/processing/ready/failed/cancelled；幂等上传、进度、取消和重试 | 重启后状态可恢复；重试不产生重复向量或孤立文件 |
| 9 | 统一搜索 | 保留，未执行 | 跨笔记、记忆、会话和知识库检索；支持类型、时间、标签和来源过滤 | 结果按用户隔离；可进入原对象；混合检索有质量基线 |
| 10 | 运行追踪、导出与恢复 | 保留，未执行 | Agent run、模型/Tool/耗时/错误记录；版本化导出；备份恢复与部署演练 | run 可诊断；导出可校验；数据库、文件和向量状态可恢复 |

## 下一轮选择

默认顺序保持为：

```text
7 -> 8 -> 9 -> 10
```

若只选择一个新功能，优先选择 `7`，因为工作包 `2` 和 `6` 已提供安全渲染及版本化 API/SSE 合同。`8-10` 仍需各自建立独立变更计划，不能因前置基础完成而视为已经实施。

每个工作包在 `project_changes/<日期-主题>/` 使用同主题目录三件套记录：`plan.md`、`change-log.md` 和 `test-record.md`。完成条件仍包括相关测试、构建、OpenAPI、migration、Benchmark、回滚说明和活文档同步更新。
