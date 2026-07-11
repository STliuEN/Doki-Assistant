# Benchmark 大规模扩展变更日志

日期：2026-07-11

## 已完成范围

- 扩展 AgentRunPlan，记录实际解析后的 `skill_ids` 和 `tool_ids`，供 Benchmark 评分和结果追踪。
- Case schema 增加 `integration` mode、manual/auto variant、路由方式、状态观测、路由合同、状态合同、效率合同、增强事件合同和 hard veto。
- Result schema 增加实际/候选 Skill、variant 和 repeat index。
- Runner 支持严格 case matrix 深合并、未知字段拒绝、全仓重复 ID 拒绝，以及 mode/tag/variant 过滤。
- Offline runner 记录消息创建、消息更新、pending action、跨用户访问和外部访问观测。
- Scorer 增加 routing precision/recall/F1、exact route match、状态副作用、Tool 调用预算、事件顺序/唯一性/终止性评分。
- 增加 `safety_veto`、`isolation_veto` 和 `external_access_veto`；命中后总分强制为 0，不能被平均分抵消。
- 报告增加 suite 分组、routing F1、hard veto 数、延迟和首个有效响应 p50/p95。
- CLI 增加 `--mode`、`--tag`、`--variant` 和 `--fail-on-veto`，保留既有 `--offline` 和 smoke 命令。
- 新增 117 个矩阵化 regression case；加上既有正向 case 后，当前正向离线 case 总数为 121。
- 新增 GuardedTool 和 pending action 边界测试，覆盖预算、确认、身份缺失、确认后执行、超时、截断、TTL、越权和一次性消费。
- CI 增加完整 offline regression gate。
- 同步根 README、Benchmark README、开发者指南、新手指南和路线图。

## 用例分布

| Suite | 正向离线 case |
| --- | ---: |
| `agent_basic` | 10 |
| `intent_routing` | 30 |
| `skill_tool_selection` | 18 |
| `tool_safety` | 22 |
| `chat_stream` | 16 |
| `context_management` | 14 |
| `error_recovery` | 10 |
| 兼容 `skill_routing` smoke | 1 |
| **合计** | **121** |

## 兼容性

- 原 4 个 smoke case 和 baseline 未修改。
- `--suite smoke --offline --fail-under 0.9` 继续可用。
- 旧 case 不声明新合同字段时，新指标按通过处理，不改变既有行为。
- Case 自定义 `expect.weights` 仍是最终覆盖；未声明的新指标权重为 0，避免升级后分数漂移。

## 未完成范围

- 真实 MySQL/Redis Integration Benchmark。
- 真实 RAG/MCP 集成环境。
- 60 条在线固定任务和 manual/auto 360 次真实模型对照。
- 新增前端 28 个合同/E2E case。

上述内容仍保留在 `plan.md` 和 `docs/roadmap_next.md`，不得把当前离线结果表述为真实用户或真实模型质量数据。
