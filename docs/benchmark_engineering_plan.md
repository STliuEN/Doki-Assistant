# Benchmark 开发者指南

日期：2026-06-30  
状态：已接入第一版离线 smoke benchmark，本文作为后续 benchmark 重构的开发入口。

## 定位

benchmark 用来验证 Agent 运行链路在重构后没有退步。它不是替代单元测试，而是把“准备运行计划、Skill/Tool 选择、SSE 流、工具安全、落库收尾、前端消费契约”串起来跑一遍。

当前第一层是 `smoke`：

- 离线执行，不调用真实 LLM。
- 使用脚本化 fake executor，不依赖外部模型、MySQL、embedding 服务或 MCP discovery。
- 复用生产链路：`prepare_agent_run`、`get_agent_stream_response`、`drive_sse_stream`、`stream_agent_events`。
- 输出结构化 result、trace JSONL、summary JSON/Markdown。

后续 `full` 层可以接真实模型和真实 RAG fixture，但不作为日常提交 gate。

## 目录结构

```text
benchmarks/
  README.md
  __init__.py
  baselines/
    smoke.baseline.json
  cases/
    agent_basic.yaml
    chat_stream.yaml
    skill_routing.yaml
    tool_safety.yaml
  fixtures/
    scripts/
      *.json
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
backend/tests/
  test_benchmark_runner.py
  test_benchmark_scoring.py
  test_chat_stream_contract.py

front/src/features/chat/__tests__/
  useChatStream.test.ts
```

## 运行命令

从 `backend/` 目录运行：

```powershell
uv run pytest tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_chat_stream_contract.py
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

开发单条 case：

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --case-id agent_basic.plain_text_001 --offline
```

不要把裸 `--offline` 当成通过/失败 gate。它会选中所有离线 case，包括用于验证 scorer 的负向 fixture，例如 `agent_basic.must_not_include_001`，该 case 预期失败。日常 gate 使用 `--suite smoke`。

前端流式测试：

```powershell
cd front
npm run test
```

## 执行链路

离线 benchmark 的核心原则是：只替换模型大脑，不替换生产编排。

```text
case YAML
  -> load_cases / select_cases
  -> prepare_agent_run
     - 可打桩 route_skills，避免真实 embedding
     - 可打桩 mcp_tool_registry.ensure_fresh，避免真实 MCP discovery
  -> FakeAgentFactory
  -> get_agent_stream_response(..., factory=fake)
  -> stream_agent_events
  -> drive_sse_stream
  -> score_case
  -> write_reports
```

`FakeAgentFactory` 返回脚本化 executor。脚本事件来自 `benchmarks/fixtures/scripts/*.json`，形状模拟 LangChain `astream_events`：

```json
[
  { "event": "on_chat_model_stream", "data": { "chunk": "answer" } },
  { "event": "call_tool", "name": "delete_memory_tool", "data": { "input": { "memory_id": "m-001" } } }
]
```

`call_tool` 是 benchmark fake executor 的扩展事件，用来触发真实 `GuardedTool.ainvoke()`，从而保留高风险确认、超时、输出截断和预算语义。

## 离线隔离

smoke benchmark 必须是本地可重复、零副作用的。

- `session_id` / `user_id` 使用 `bench-{run_id}`。
- `session_manager` 使用内存桩，避免写 MySQL。
- `route_skills` 可以被 case 的 `input.routed_skill_ids` 固定，避免本地 embedding 波动。
- `mcp_tool_registry.ensure_fresh()` 固定为 no-op，避免连接 MCP server。
- `save_pending_action` 使用内存桩，避免写 Redis 或数据库。
- 运行产物写入 `benchmarks/results/`，只提交 `.gitkeep`。

如果未来需要覆盖真实持久化层，应新建 full/integration 层，不要改 smoke 的零依赖假设。注意 `database_session_manager.py` 直接导入 `AsyncSessionLocal`，只 patch `app.db.db_config.AsyncSessionLocal` 不会影响已绑定的使用方符号。

## Case 约定

每个 YAML 文件包含一个 `cases` 列表：

```yaml
cases:
  - id: tool_safety.delete_memory_blocked_001
    suite: tool_safety
    title: High-risk delete memory tool is blocked as waiting confirmation
    mode: offline
    input:
      query: "Delete memory item m-001."
      prompt_type: main_prompt
      skill_ids: ["memory_write"]
      tool_ids: ["delete_memory"]
      routed_skill_ids: ["memory_write"]
      context:
        mode: current_only
      rag_retrieval:
        mode: auto
    fixtures:
      model_script: fixtures/scripts/tool_safety_delete_memory_blocked_001.json
    expect:
      must_include: ["confirmation"]
      must_not_include: []
      tool_policy:
        allowed: ["delete_memory"]
        forbidden_call: []
        forbidden_execute: ["delete_memory"]
        expect_blocked: ["delete_memory"]
      event_contract:
        first_event_type: response
        require_done_session_id: true
        require_response_before_done: true
      stop_reason: completed
      min_score: 0.9
    tags: [smoke, tool_safety, no_external_network]
```

字段语义：

- `id` 全局唯一，建议 `suite.name_001`。
- `suite` 决定默认评分权重。
- `mode: offline` 代表必须可在 smoke 中无外部依赖运行。
- `fixtures.model_script` 相对 `benchmarks/`。
- `tags: [smoke]` 表示该 case 必须通过 smoke gate。
- `tags: [negative]` 表示该 case 用来验证 scorer 失败路径，不进入 smoke gate。
- `input.tool_ids` 是显式工具选择，会跳过语义路由，但当前仍会合并所选 skill 自带工具；case 断言应针对 `prepared_tool_ids` 的实际语义。

## Scorer 语义

`score_case` 组合五类指标：

- `must_include_score`
- `forbidden_content_score`
- `event_contract_score`
- `tool_policy_score`
- `stop_reason_score`

硬否决项：

- 出现 `must_not_include` 内容。
- 命中 `forbidden_call`。
- 命中 `forbidden_execute`。

`tool_safety` 的核心是区分“调用”和“执行”：

- `forbidden_call`：连发起调用都不允许。
- `forbidden_execute`：允许模型尝试调用，但必须被 `GuardedTool` 拦住，不能真正执行。
- `expect_blocked`：必须出现 `waiting_confirmation`。

安全正例应该让模型尝试调用高风险工具，并断言它被拦住。不要把“尝试调用但被拦住”当失败。

## SSE 契约

后端 `drive_sse_stream` 起手固定发送一个空 response：

```json
{"type": "response", "content": "", "session_id": "..."}
```

因此：

- `first_event_type: response` 只证明 SSE 入口帧存在。
- 首响应延迟必须使用 `first_non_empty_response_ms`，跳过空 response。
- 如果 case 要证明模型产生了用户可见内容，应检查非空 response，而不是只检查 `require_response_before_done`。
- 所有 `done` 事件应携带 `session_id`，错误路径也要保持一致。

当前已补后端测试锁定错误路径和异常路径的 `done.session_id`。

## 已知重构边界

这几处是后续需要继续收紧的点：

- 默认 `--offline` 会包含负向 fixture，不能作为 gate。可考虑新增 `--include-negative` 或默认排除 `negative` tag。
- `forbidden_execute` 目前基于工具集合判断，后续应按 `tool_call_index` 或事件顺序判定，避免同名工具“先 blocked 后 executed”被漏判。
- `require_response_before_done` 当前会被起手空 response 满足，后续应增加 `require_non_empty_response_before_done`。
- `skill_routing` 离线 case 只能测显式 `tool_ids` 或确定性关键词路径；真实 embedding 语义路由应放进 online/full。
- 真实 RAG benchmark 必须使用固定 fixture，不得读取真实用户知识库。

## 新增 Case 流程

1. 选择 suite，并判断是否能离线。
2. 写 `benchmarks/cases/<suite>.yaml` case。
3. 写对应 `benchmarks/fixtures/scripts/<case_id>.json`。
4. 单跑 `--case-id`，确认 result 和 trace。
5. 如果进入日常 gate，加 `smoke` tag 并更新 `baselines/smoke.baseline.json`。
6. 为 scorer 新边界补 `backend/tests/test_benchmark_scoring.py`。

提交前至少运行：

```powershell
cd backend
uv run pytest tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_chat_stream_contract.py
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

若改了前端 SSE 消费：

```powershell
cd front
npm run test
```

## 报告与 Baseline

每次运行会生成：

```text
benchmarks/results/<timestamp>/
  <run_id>.trace.jsonl
  summary.json
  summary.md
```

`summary.json` 包含每个 case 的 score、status、errors、metrics、flags 和 baseline delta。`summary.md` 面向人工 review。

`benchmarks/baselines/smoke.baseline.json` 是小型稳定基线，应提交进仓库。运行产物不要提交。

## 与其他文档的关系

- [benchmark_starter_guide.md](benchmark_starter_guide.md)：给非工程读者理解概念和上手步骤。
- [development_setup.md](development_setup.md)：放日常开发命令入口。
- [project_develop.md](project_develop.md)：描述 benchmark 在整体架构中的位置。
- `benchmarks/README.md`：放最短运行说明和目录内注意事项。
