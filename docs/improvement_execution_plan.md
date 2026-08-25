# 改进执行计划

状态：工作包 `1-6` 已完成；工作包 `11`（`SK-0` 至 `SK-5`）为当前必须执行的最高优先级核心重构；工作包 `7-10` 冻结

最近复核：2026-08-24

适用范围：当前 `ai_document_assistant` 分支

本文把 [全量重构开发计划](./roadmap_next.md) 和 [安全与可靠性加固计划](./security_hardening_plan.md) 转换为可独立执行、验收和回滚的工作包。当前运行事实见[当前架构](./project_develop.md)；架构重写的阶段顺序、可靠性合同、数据权威矩阵和 `ARCH-GATE` 以[架构重写计划](./architecture_rewrite_plan.md)为唯一事实源。`1-6` 已完成，实施证据保存在 `project_changes/`；`7-10` 只有在 `SKILL-GATE` 和 `ARCH-GATE` 都通过后才可选择。工作包 `11` 不属于冻结产品队列，而是贯穿当前 AR 阶段的核心重构，详细合同见[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)。

## 架构重写与 Skill 核心门禁

在架构重写完成前，不实施工作包 `7-10` 或其他普通产品功能。工作包 `11` 是明确的核心例外，但不能绕过可靠性依赖；当前执行主线固定为：

```text
AR-0 + SK-0（合同、威胁、inventory、characterization）
  -> AR-1 + SK-1（运行时底座、标准 parser、领域骨架）
  -> AR-2/AR-3（角色、审计、统一 schema/UoW）
  -> AR-4 + SK-2（canonical package Storage、生命周期、可视化管理）
  -> AR-5 starts with skills/tools/mcp + SK-3（A/B 运行、一次性迁移）
  -> SK-4（C 级隔离执行）
  -> AR-6 + SK-5（canary、切换、旧能力退出）
  -> SKILL-GATE
  -> ARCH-GATE
  -> 7 -> 8 -> 9 -> 10
```

每个阶段必须具备入口条件、产物、验证、回滚点和退出门。Skill 专项所需基础未满足时，优先补齐对应 AR 阶段，不得改做 `7-10`。任何状态冲突以架构重写计划为准。

### 当前必须执行的 Skill 与可靠性底座

以下工作共同构成工作包 `11` 和 AR 阶段的必做范围：

- API 与 worker 独立进程、连接池、模型和并发资源预算；
- MySQL outbox/job 的持久状态、原子 claim、lease/heartbeat、fencing、重试、DLQ、取消、背压和重启恢复；
- application-layer UoW、outbox 与业务事实同事务，以及禁止 router/repository 直写 commit 的检查；
- 分层 readiness、request/run/job/event correlation、SLO/RPO/RTO 指标和告警；
- SSE `event_id`/cursor/replay 或 polling fallback；
- Storage immutable object、checksum、atomic finalize、generation manifest，以及 Chroma quarantine、版本投影、对账和重建；
- 标准 Skill 格式/威胁合同、不可变 package 存储、capability grant、隔离 runner、Registry revision、一次性旧 Skill 迁移和可视化管理；
- kill/restart、依赖超时、Redis 丢失、磁盘满、重复投递和恢复演练。

标准 Skill A/B/C 能力和管理前端必须在 `ARCH-GATE` 前按 `SK-0` 至 `SK-5` 完成并通过 `SKILL-GATE`。这不解锁工作包 `7-10`。

## 当前验证基线

| 检查 | 2026-08-24 最终复跑结果 |
|------|--------------------|
| Backend pytest | `216 passed` |
| Backend 静态/依赖 | Ruff、compileall、`uv lock --check` 和 requirements 检查通过 |
| FastAPI OpenAPI | current，生成文件检查通过 |
| Alembic | 单一 head `20260824_0002`；upgrade/downgrade offline SQL 通过 |
| Django tests | 隔离 SQLite 与 LocMemCache，`19 passed` |
| Frontend Vitest | `6 files / 28 tests passed` |
| Frontend lint / build | passed |
| Offline Benchmark | smoke `4/4`；regression `117/117`，hard veto `0` |
| 文档与差异 | `143 files / 132 local links`；`git diff --check` 通过 |

`scripts/check-docs.ps1` 已过滤 Git 索引中存在但工作树已删除的 cached 路径，文档结果只统计当前工作树。Benchmark results、前端 `dist` 和其他中间产物均受 ignore 规则保护，没有进入跟踪清单。

数据库相关验证只使用临时 SQLite、Alembic offline SQL 和 revision 检查，没有连接或修改现有 MySQL。浏览器验收未启动 FastAPI，因此没有读取业务 MySQL；笔记页请求出现预期的 `502`，不计为已覆盖的业务主流程。上述结果只是合同/离线基线，不证明真实 MySQL、Redis、Storage、Chroma 的迁移、故障恢复、容量或 RPO/RTO。

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
| 7 | 回答引用与一键沉淀 | 冻结，待 `ARCH-GATE` | SSE 返回文档、页码、chunk 和得分；前端来源抽屉；回答保存为笔记或记忆并保留来源 | 引用可回到原文；保存结果可追溯；越权来源不可见 |
| 8 | 知识处理任务中心 | 产品 UI/API 冻结；底层任务基础前置 | 持久化 queued/processing/ready/failed/cancelled；幂等上传、进度、取消和重试 | AR-1/AR-4 先证明重启恢复、lease/fencing、背压和投影对账；`ARCH-GATE` 后再交付 UI |
| 9 | 统一搜索 | 冻结，待 `ARCH-GATE` | 跨笔记、记忆、会话和知识库检索；支持类型、时间、标签和来源过滤 | 结果按用户隔离；可进入原对象；混合检索有质量基线 |
| 10 | 运行追踪、导出与恢复 | 产品 UI/API 冻结；观测/恢复底座前置 | Agent run、模型/Tool/耗时/错误记录；版本化导出；备份恢复与部署演练 | AR-0/AR-1/AR-6 先完成 correlation、manifest、恢复和演练；`ARCH-GATE` 后再交付 UI |
| 11 | 标准兼容 Skill 单轨重构 | A 级与有限 B 级开发支持已形成；门禁未通过 | parser/Storage/领域/API/UI/seed、资源编辑、CapabilityGrant、SkillRunBinding、private 过滤、多实例 reconcile 和旧运行目录退出已落地；保留 durable import、per-user scope、累计 token 预算、C runner 与真实 E2E | `SKILL-GATE`：标准导入/编辑/导出、A/B/C、安全隔离、迁移对账、回滚和无 Git 运行写入全部通过 |

## 当前执行选择

当前没有可选择的 `7-10` 产品 UI/API。工作包 `11` 已被确定为当前最高优先级核心修改，内部顺序固定为：

```text
SK-0 -> SK-1 -> SK-2 -> SK-3 -> SK-4 -> SK-5 -> SKILL-GATE
  -> ARCH-GATE -> 7 -> 8 -> 9 -> 10
```

现有实现不能替代阶段门禁：CapabilityGrant、SkillRunBinding、private Skill/Tool 过滤、资源编辑、多实例 reconcile、OpenAPI 和旧路径静态禁回归已经完成；下一步集中补 durable import worker、per-user scope、资源累计 token 预算，以及真实 MySQL/API/第三方 A/B 聊天 E2E。`SK-4` 只有在独立 runner/沙箱、依赖锁定、权限和强制终止验收后才开放 Node/Python 脚本。工作包 `7-10` 原范围完整保留，不能因 Skill 或可靠性底座部分完成而视为已经实施。

每个工作包在 `project_changes/<日期-主题>/` 使用同主题目录三件套记录：`plan.md`、`change-log.md` 和 `test-record.md`。完成条件仍包括相关测试、构建、OpenAPI、migration、Benchmark、回滚说明和活文档同步更新。
