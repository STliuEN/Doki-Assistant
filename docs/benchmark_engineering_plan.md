# Benchmark 开发者指南

本指南说明当前本地 Benchmark 的结构、运行方式、离线隔离、评分语义和扩展流程。历史 B1-B10 建设过程保留在 Git 历史和 `project_changes/`，不再作为待办维护。

## 定位

Benchmark 用于保护 Agent 的跨模块行为合同：

- AgentRunPlan 准备。
- Skill/Tool 选择。
- AgentExecutor 事件到 SSE 的转换。
- 高风险 Tool 阻断。
- 回答和完成事件顺序。
- 落库收尾编排入口。
- 前端 SSE 消费合同。

它不替代单元测试，也不在默认层评估真实 LLM 的开放式回答质量。

## 当前层级

默认层是 `smoke`：

- `mode: offline`。
- 不调用真实 LLM。
- 不连接真实 MySQL、Embedding 或 MCP discovery。
- 工具数据来自 case fixture。
- 使用 FakeAgentFactory，但复用生产 `prepare_agent_run`、`get_agent_stream_response`、`stream_agent_events` 和 `drive_sse_stream`。
- 真实消息落库由内存 session manager 替代，只验证收尾入口。

除 4 个快速 smoke case 外，当前还提供 117 个 `regression` 标签 case。正向离线 case 总数为 121，覆盖正常/否定/疑问/模糊/多意图表达、18 个本地 Tool 装配、高风险确认、SSE、上下文设置和工具错误恢复。

真实模型、真实 RAG 和数据库集成层尚未实现，不应混入默认 smoke gate。

## 目录

```text
benchmarks/
  README.md
  suites.yaml
  baselines/
    smoke.baseline.json
  cases/
    agent_basic.yaml
    chat_stream.yaml
    regression_matrix.yaml
    skill_routing.yaml
    tool_safety.yaml
  fixtures/
    scripts/*.json
  runners/
    fake_factory.py
    harness.py
    report_results.py
    run_benchmarks.py
    score_cases.py
  schemas/
    case.schema.json
    result.schema.json
  results/
    .gitkeep
```

配套测试：

```text
backend/tests/test_benchmark_runner.py
backend/tests/test_benchmark_scoring.py
backend/tests/test_benchmark_reporting.py
backend/tests/test_chat_stream_contract.py
backend/tests/test_tool_guard.py
backend/tests/test_pending_action_store.py
front/src/features/chat/__tests__/useChatStream.test.ts
```

## 运行

从 `backend/` 执行：

```powershell
uv run pytest tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_chat_stream_contract.py
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
uv run python ..\benchmarks\runners\run_benchmarks.py --mode offline --tag regression --fail-on-veto
```

单 case：

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --case-id agent_basic.plain_text_001 --offline
```

参数：

| 参数 | 语义 |
|------|------|
| `--suite <name>` | 选择 suite；`smoke` 按 tag 选择 |
| `--case-id <id>` | 精确选择一个 case |
| `--offline` | 只选择 `mode: offline` |
| `--mode <mode>` | 选择 `offline/integration/online`；当前可执行 case 位于 offline |
| `--tag <tag>` | 只选择包含该 tag 的 case |
| `--variant <variant>` | 选择 `manual/auto` 变体，为在线对照层预留 |
| `--include-negative` | 包含用于验证 scorer 失败路径的 negative case |
| `--repeat N` | 重复执行 |
| `--output-dir PATH` | 报告目录 |
| `--fail-under SCORE` | 平均分低于阈值时退出非零 |
| `--fail-on-veto` | 任一 `safety/isolation/external_access` hard veto 时退出非零 |

negative case 默认排除。裸 `--offline` 的范围仍比 `--suite smoke` 广，日常 gate 应显式使用 smoke suite。

验证 negative scorer fixture：

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --offline --include-negative
```

## 执行链路

```text
load case YAML
  -> expand strict case matrices
  -> JSON Schema validation
  -> merge suite/case weights
  -> select_cases
  -> offline_patches
  -> prepare_agent_run
  -> FakeAgentFactory
  -> get_agent_stream_response
  -> stream_agent_events
  -> drive_sse_stream
  -> parse SSE and write trace
  -> score_case
  -> write result and summary
```

离线原则是“替换模型和外部依赖，不替换生产编排”。如果一个 case 绕开 `prepare_agent_run` 或 SSE driver，它更适合成为单元测试，而不是本层 Benchmark。

## Case 结构

最小示例：

```yaml
cases:
  - id: agent_basic.example_001
    title: basic example
    suite: agent_basic
    mode: offline
    input:
      query: "hello"
      context:
        mode: current_only
      rag_retrieval:
        mode: auto
    fixtures:
      model_script: fixtures/scripts/agent_basic_example_001.json
    expect:
      must_include: ["hello"]
      must_not_include: []
      event_contract:
        first_event_type: response
        require_done_session_id: true
        require_non_empty_response_before_done: true
      min_score: 0.9
    tags: [smoke, agent, no_external_network]
```

加载时使用 `schemas/case.schema.json` 校验。`tool_policy`、`event_contract` 等受限对象出现未知字段会直接失败，不会被静默忽略。

### Case matrix

大量同类边界场景使用 `matrices` 表达。`defaults` 提供完整合法 case，`rows` 只覆盖变化字段；加载器执行深合并、补全 `id_prefix`、逐 case 运行 JSON Schema，并拒绝未知 matrix 字段和全仓重复 ID。矩阵行仍是独立 logical case，报告和 trace 中各有单独 ID。

```yaml
matrices:
  - id_prefix: agent_basic.boundary
    defaults:
      suite: agent_basic
      title: boundary
      mode: offline
      input: {query: default}
      fixtures: {model_script: fixtures/scripts/shared_benchmark_response.json}
      expect: {event_contract: {terminal_type: done}}
      tags: [regression]
    rows:
      - {id: unicode, input: {query: "你好 👋"}}
      - {id: multiline, input: {query: "第一行\n第二行"}}
```

## Fixture

### 模型脚本

`fixtures.model_script` 指向 JSON 事件数组，形状模拟 LangChain `astream_events(version="v2")`。

```json
[
  {
    "event": "on_chat_model_stream",
    "data": {"chunk": "hello"}
  }
]
```

FakeAgentFactory 返回脚本化 executor，生产 event pump 仍负责把事件转换成 Doki SSE。

### 工具数据

普通 DB/RAG 邻接工具必须使用 `fixtures.tool_data`。例如 memory fixture 会替换真实 AsyncSession/MemoryService，禁止访问真实用户数据。

```yaml
fixtures:
  tool_data:
    memories:
      - id: mem-fixture-001
        title: Example
        type: todo
```

新增会访问数据库、向量库、网络或文件系统的工具 case 时，必须先提供明确隔离层；否则放入未来 integration/full 层。

## Offline patches

`harness.offline_patches` 当前负责：

- 内存 session manager。
- fixture AsyncSession/MemoryService。
- 确定性 Skill 路由替身。
- 禁止真实 MCP discovery。
- 使用 case Tool 数据。
- 注入 FakeAgentFactory。

`fixtures.routing.mode` 控制路由方式：

- `scripted`：使用 `input.routed_skill_ids` 固定路由结果，验证后续 Skill/Tool 装配和运行合同。
- `production`：不替换 `route_skills`，用于可确定的生产关键词路由回归。

脚本路由 case 不能作为真实语义路由准确率证据。真实 Embedding/LLM 路由质量仍属于 online 层。

测试需要能够证明真实 MySQL、向量库和外部网络没有被访问。仅在文档中声明“离线”不算隔离。

## Scorer

评分项：

| 项 | 作用 |
|----|------|
| `must_include_score` | 必需内容是否出现 |
| `forbidden_content_score` | 禁止内容是否未出现 |
| `event_contract_score` | SSE 顺序和必需事件 |
| `tool_policy_score` | Tool 允许、禁止、阻断和执行语义 |
| `stop_reason_score` | 停止原因 |
| `routing_contract_score` | 实际 Skill/Tool 装配集合 |
| `state_contract_score` | 消息、更新和 pending action 副作用计数 |
| `efficiency_score` | Tool 调用次数上下界 |

此外，报告单独输出 `routing_precision/recall/F1` 和 exact route match。`hard_vetoes` 不参与加权：危险 Tool 真正执行、跨用户访问或离线外部访问一旦出现，case 立即归零失败。

suite 默认权重位于 `benchmarks/suites.yaml`。case 可以用 `expect.weights` 覆盖。权重必须是非负数且总和大于零。

### 内容断言

- `must_include`：每个字符串必须出现在最终 response text。
- `must_not_include`：任一字符串出现即触发硬失败。

这些是稳定工程断言，不适合评估同义表达或开放式质量。

### Tool policy

合法字段：

```yaml
tool_policy:
  allowed: []
  forbidden_call: []
  forbidden_execute: []
  expect_blocked: []
```

语义：

- `allowed`：准备或调用的 Tool 必须位于允许集。
- `forbidden_call`：不得出现对应 tool_start。
- `forbidden_execute`：可以尝试，但不能发生未阻断的真实执行。
- `expect_blocked`：必须出现对应 waiting_confirmation/blocked 证据。

`forbidden_execute` 按事件顺序和单次调用配对判断。同名工具先被阻断、随后又执行时，仍会正确失败。

### Event contract

常用字段：

- `first_event_type`。
- `require_done_session_id`。
- `require_response_before_done`。
- `require_non_empty_response_before_done`。
- `ordered_types`：指定必须按顺序出现的事件子序列。
- `exactly_once`：指定必须且只能出现一次的事件类型。
- `forbidden_types`：禁止出现的事件类型。
- `terminal_type`：最后一个事件的类型。

SSE driver 固定先发送空 response，因此证明用户可见内容时必须使用 `require_non_empty_response_before_done`，不能只用 `require_response_before_done`。

所有正常、异常和错误路径的 `done` 都应携带 `session_id`。

## Trace 与结果

每次运行在 `benchmarks/results/<timestamp>/` 生成：

- 每个 run 的 trace JSONL。
- case result。
- `summary.json`。
- `summary.md`。

汇总报告包含 suite 分组、routing F1、hard veto 数，以及总耗时和首个有效响应的 p50/p95。

Trace 用于调试事件顺序，不应包含真实用户数据、secret 或无限制 Tool 输出。

`benchmarks/results/` 被忽略，只提交 `.gitkeep`。

## Baseline

当前 smoke baseline：

```text
benchmarks/baselines/smoke.baseline.json
```

它包含四个应通过 case：

- `agent_basic.plain_text_001`。
- `chat_stream.chunk_done_001`。
- `skill_routing.explicit_tool_ids_001`。
- `tool_safety.delete_memory_blocked_001`。

只有确认行为变化符合预期时才更新 baseline。不要用更新 baseline 隐藏回归。

## 新增 Case

1. 确定它是单元测试、offline smoke 还是未来 integration/full case。
2. 在对应 YAML 中添加唯一 ID。
3. 创建模型脚本和必要工具 fixture。
4. 使用 `--case-id` 单跑。
5. 检查 trace，而不只看总分。
6. 为 scorer/schema 新语义补单元测试。
7. 只有稳定、离线、无真实副作用的 case 才加 `smoke` tag。
8. 确认后更新 baseline。

## 修改 Scorer

修改评分前必须：

- 为通过和失败各增加测试。
- 显式运行 `--include-negative`。
- 检查已有 baseline 是否因语义变化而变化。
- 同步更新 `case.schema.json` 和本文。

```powershell
cd backend
uv run pytest tests\test_benchmark_scoring.py tests\test_benchmark_runner.py
uv run python ..\benchmarks\runners\run_benchmarks.py --offline --include-negative
```

## 前端合同

Benchmark runner 不运行浏览器。前端 SSE 合同由 Vitest 单独保护：

```powershell
cd front
npm run test
```

后端改变事件类型、flush 顺序、`session_id` 或 regenerate 语义时，必须同时运行后端合同测试和前端测试。

## 当前限制

- smoke 只覆盖脚本化模型，不评估真实模型质量。
- 真实 embedding 语义路由不属于 offline 层。
- 真实 RAG/MySQL/Redis/MCP 集成层尚未建立。
- 当前 case 数量较少，主要保护运行时工程合同。
- offline 中大部分意图表达 case 使用脚本路由，不能替代真实 Embedding 路由质量评估。
- 没有 CI 自动运行 smoke gate。

扩展优先级见 [全量重构开发计划的质量门禁阶段](./roadmap_next.md#r7-质量性能与运维门禁)。
