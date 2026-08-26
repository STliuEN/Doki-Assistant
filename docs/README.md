# 文档索引

本目录只维护与当前代码一致的活文档。`project_changes/` 保存历史方案、变更日志和测试记录，用于追溯，不作为当前架构或操作方式的事实来源。

2026-08-25 复核：基础工作包 `1-6` 只是保护性切片，当前停留在 `AR-0 + SK-0`，发布原子性、Registry 单包隔离、授权撤销与完整审计、Skill OpenAPI、Chroma 安全恢复、通用 worker/UoW 和真实依赖基线仍阻断后续阶段。A 级与有限 B 级代码切片不等于多实例闭环、统一 stale `503` 或 OpenAPI 合同已经完成；旧 Skill 目录提前删除及固定 seed 也不等于通用迁移完成。工作包 `7-10` 只暂停到本地 A/B `SKILL-GATE` 与本地 `ARCH-GATE`；C 级与公网/HA 分别由 `EXEC-SKILL-GATE`、`PUBLIC-HA-GATE` 独立控制，本地门不会解锁它们，它们也不反向冻结本地产品开发。

## 阅读顺序

| 读者/任务 | 文档 |
|-----------|------|
| 第一次运行项目 | [开发与运行说明](./development_setup.md) |
| 理解服务和模块边界 | [当前架构](./project_develop.md) |
| 修改聊天、SSE 或上下文 | [Agent 运行时](./agent_runtime_improvements.md) |
| 接入或管理 MCP | [MCP 接入与管理](./mcp_integration_plan.md) |
| 查看标准 Skill 当前兼容等级、实现差距和验收门 | [标准 Skill 接入需求规格](./standard_skill_integration_requirements.md) |
| 修改记忆中心 | [记忆中心](./memory_center_implementation.md) |
| 配置本地 Reranker | [本地模型配置](./modelscope_model.md) |
| 排查运行问题 | [故障排除](./troubleshooting.md) |
| 运行或扩展 Benchmark | [Benchmark 开发者指南](./benchmark_engineering_plan.md) |
| 第一次理解 Benchmark | [Benchmark 新手指南](./benchmark_starter_guide.md) |
| 查看当前 AR/SK 状态、数据权威和分层门禁 | [架构重写计划](./architecture_rewrite_plan.md) |
| 查看 R0-R8 职责和产品工作包 `7-10` | [产品路线图](./roadmap_next.md) |
| 查看已落地控制和剩余安全、部署与恢复风险 | [安全与可靠性加固计划](./security_hardening_plan.md) |

用户服务接口单独维护在 [DjangoUserService API](../DjangoUserService/api.md)。前端开发入口见 [front/README.md](../front/README.md)。

## 事实来源优先级

出现冲突时按以下顺序判断：

1. 运行代码、路由定义和 schema。
2. `pyproject.toml`、`package.json`、lock 文件和 `.env.example`。
3. [架构重写计划](./architecture_rewrite_plan.md)中的阶段、门禁和当前队列。
4. 本目录中的其他活文档。
5. 根 `README.md` 的概览。
6. `project_changes/` 中的历史记录。

文档中的版本号、环境变量、端口、命令和文件路径应能在前两类来源中找到对应依据。

## 维护约定

- AR/SK 状态、门禁和当前队列只在架构重写计划维护；产品路线图只维护 R0-R8 职责和产品队列。
- 已完成的工作包在历史记录中保留 plan、change log 和 test record；未执行项不得提前标记完成。
- 本地 `ARCH-GATE` 未通过前，不得把 `7-10` 或其他本地产品功能标记为可执行；A/B Skill 主线仍必须遵守 AR 依赖。通过本地门不自动解锁 C 级或公网/HA，后二者分别以 `EXEC-SKILL-GATE` 和 `PUBLIC-HA-GATE` 为准。
- 不再使用的配置文件必须明确标记为 legacy，不能继续列为有效入口。
- `README.md` 保持概览；实现细节写入对应专题文档。
- 变更 API、环境变量、启动命令、SSE 事件或目录结构时，同一提交更新相关文档。
- 新文档优先链接真实文件，避免复制容易漂移的大段配置。
