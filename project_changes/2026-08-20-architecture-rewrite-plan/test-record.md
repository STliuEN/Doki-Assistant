# 架构重写计划文档化验证记录

日期：2026-08-20

状态：完成（计划修订验证；架构阶段未执行）

## 已执行检查

- 只读审阅当前 README、文档索引、当前架构、开发说明、路线图和改进执行计划。
- 确认工作树在编辑前干净。
- 使用 `scripts/check-docs.ps1` 检查 Markdown 代码围栏和本地链接；可靠性修订后的最终结果为 `139 files, 121 local links`。
- 使用 `git diff --check` 检查空白错误。
- 使用 `git status --short` 确认仅有计划文档和历史记录变更。
- 使用 `rg` 复核活文档中不存在“可直接选择/执行 7-10”的旧门禁表述；剩余引用均明确标记为冻结或解锁条件。

## 可靠性优先修订复核

- 只读对照 `architecture_rewrite_plan.md`、`roadmap_next.md` 和 `improvement_execution_plan.md`，确认 AR 顺序一致为 AR-0 可靠性契约/P0 止血、AR-1 API/worker 隔离与持久任务、AR-2 身份、AR-3 关系迁移、AR-4 Storage/索引投影、AR-5 模块化、AR-6 灰度/HA/停用。
- 使用 `rg` 检查旧的“optional worker”“先测量再引入 worker”“AR-4 模块化后 AR-5 才建立任务基础”等冲突表述已移除或改为历史/过渡说明。
- 复核工作包 8/10：产品 UI/API 仍标记冻结；durable job、SSE replay、readiness、manifest 和恢复演练明确为门禁前允许且必须完成的基础。
- 复核 ARCH-GATE：包含数值 SLO/RPO/RTO、跨存储恢复、迁移增量重放、认证持久事实、投影 fencing、组合故障和 canary/restore-forward 证据要求。
- 未运行真实 MySQL、Redis、Storage、Chroma、模型或 MCP；未执行迁移、服务切换、删除或代码实现。

## 数据安全

本次验证未连接、读取或修改现有 MySQL；未访问生产 Redis、Chroma 或用户文件。没有执行服务启动、migration、数据迁移或删除操作。

## 未覆盖项

架构阶段尚未实施，因此 AR-0 之后的数据清单、迁移脚本、恢复演练、性能基线和 `ARCH-GATE` 验收结果均待后续独立变更记录。
