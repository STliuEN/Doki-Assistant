# 工作计划与代码现实校准变更记录

日期：2026-08-25

状态：已记录（仅文档；当前批次证据不等于业务实现完成）

## 已确认的现实基线

- 当前分支相对 `ai_document_assistant_develop` 多 33 个提交，涉及 377 个文件。
- 后端复跑为 `216 passed`；Ruff、OpenAPI 生成检查、`uv lock --check` 和文档检查通过。
- 当前 shell 找不到 Node/npm，未把历史前端结果冒充本轮复跑结果。
- import 仍在 API 请求内同步执行，仓库没有独立 worker 入口。
- Chroma 初始化失败仍可能递归删除持久目录。
- 损坏 Skill package 可形成 ready/degraded 空 Registry；授权、撤销、完整审计、Tool/MCP policy 固定和 Skill import/export 合同仍有缺口。
- 当前 lock 与 CI 是 Windows-only，不能提供 Linux 或泛化的跨平台证据。

## 文档变更

- 本批原计划仅校准活文档，未修改 Python、TypeScript、PowerShell、workflow、依赖或数据库。
- 08-25 批次的最终差异审查在批次结束时未完成；其“仅修改 Markdown”的范围声明不能覆盖后续工作树中的业务改动，也不能作为当前基线证明。
- 2026-08-26 交叉评审确认后续执行必须使用固定 commit、工作树状态、逐文件归属、scoped diff 和 hash；相关临时入口为 `docs/change-route-execution-plan-2026-08-26.md`，证据目录为 `project_changes/2026-08-26-change-route-execution/`。
- 前端、真实 MySQL/Redis/Storage/Chroma、跨平台和故障恢复结果均保持“未验证”，不得从历史记录推导当前通过。

## 未执行

- 未修改业务实现、测试行为、依赖、CI 或数据库。
- 未执行 migration、服务切换、外部消息、删除或数据恢复。
- 未宣称任何 AR/SK 阶段或门禁完成。
- 当前工作树存在后续业务/测试改动；本记录不负责为这些改动建立批次归属或验收证据。
