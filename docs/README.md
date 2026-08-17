# 文档索引

本目录只维护与当前代码一致的活文档。`project_changes/` 保存历史方案、变更日志和测试记录，用于追溯，不作为当前架构或操作方式的事实来源。

## 阅读顺序

| 读者/任务 | 文档 |
|-----------|------|
| 第一次运行项目 | [开发与运行说明](./development_setup.md) |
| 理解服务和模块边界 | [当前架构](./project_develop.md) |
| 修改聊天、SSE 或上下文 | [Agent 运行时](./agent_runtime_improvements.md) |
| 接入或管理 MCP | [MCP 接入与管理](./mcp_integration_plan.md) |
| 修改记忆中心 | [记忆中心](./memory_center_implementation.md) |
| 配置本地 Reranker | [本地模型配置](./modelscope_model.md) |
| 排查运行问题 | [故障排除](./troubleshooting.md) |
| 运行或扩展 Benchmark | [Benchmark 开发者指南](./benchmark_engineering_plan.md) |
| 第一次理解 Benchmark | [Benchmark 新手指南](./benchmark_starter_guide.md) |
| 选择下一项可执行工作 | [改进执行选择](./improvement_execution_plan.md) |
| 查看目标架构、阶段依赖和全部重构工作 | [全量重构开发计划](./roadmap_next.md) |
| 修复安全、认证、路径、部署与 migration 风险 | [安全与可靠性加固计划](./security_hardening_plan.md) |
| 修复依赖、OpenAPI、配置、lint 与 CI 漂移 | [仓库更新完整性整改计划](./maintenance_update_plan.md) |

用户服务接口单独维护在 [DjangoUserService API](../DjangoUserService/api.md)。前端开发入口见 [front/README.md](../front/README.md)。

## 事实来源优先级

出现冲突时按以下顺序判断：

1. 运行代码、路由定义和 schema。
2. `pyproject.toml`、`package.json`、lock 文件和 `.env.example`。
3. 本目录中的活文档。
4. 根 `README.md` 的概览。
5. `project_changes/` 中的历史记录。

文档中的版本号、环境变量、端口、命令和文件路径应能在前两类来源中找到对应依据。

## 维护约定

- 已完成的计划应从路线图移出，并在历史记录中保留执行证据。
- 不再使用的配置文件必须明确标记为 legacy，不能继续列为有效入口。
- `README.md` 保持概览；实现细节写入对应专题文档。
- 变更 API、环境变量、启动命令、SSE 事件或目录结构时，同一提交更新相关文档。
- 新文档优先链接真实文件，避免复制容易漂移的大段配置。
