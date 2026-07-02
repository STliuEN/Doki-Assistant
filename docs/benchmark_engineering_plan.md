# Benchmark 开发者指南

日期：2026-06-30（重构计划更新：2026-07-02）  
状态：B1–B5（离线 smoke benchmark 第一版）已接入 `ai_document_assistant` 分支。本文既是开发入口（参考部分），也是后续重构的计划入口（见「改进计划 Backlog」）。

阅读导航：

- 只想跑起来 / 查语义 → 「运行命令」「执行链路」「Scorer 语义」「SSE 契约」。
- 想知道接下来改什么、按什么优先级改 → 直接跳「进度」和「改进计划 Backlog」。

## 定位

benchmark 用来验证 Agent 运行链路在重构后没有退步。它不是替代单元测试，而是把“准备运行计划、Skill/Tool 选择、SSE 流、工具安全、落库收尾编排入口、前端消费契约”串起来跑一遍。

当前第一层是 `smoke`：

- 离线执行，不调用真实 LLM。
- 使用脚本化 fake executor，不依赖外部模型、MySQL、embedding 服务或 MCP discovery。
- 复用生产链路：`prepare_agent_run`、`get_agent_stream_response`、`drive_sse_stream`、`stream_agent_events`。
- 落库收尾只验证 `on_success` / `session_manager` 编排入口，smoke 不验证真实持久化写入。
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
- 普通工具若直接导入 `AsyncSessionLocal` 或真实 RAG/vector store，必须先接入 fixture/桩；否则不得加入 smoke。
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

## 进度

已完成（B1–B5，第一版离线 smoke benchmark）：

- B1 目录骨架与 case/schema/baseline 布局。
- B2 离线注入接缝：`FakeAgentFactory` 经 `get_agent_stream_response(..., factory=)` 注入，复用真实 `drive_sse_stream` / `stream_agent_events` / `GuardedTool` 链路。
- B3 Scorer：`must_include` / `must_not_include` / `event_contract` / `tool_policy` / `stop_reason` 五类指标 + 硬否决。
- B4 批量运行与报告：`run_benchmarks.py` + `report_results.py` 输出 trace JSONL、`summary.json` / `summary.md`。
- B5 Baseline 回归对比：`baselines/smoke.baseline.json` + summary 中的 `score_delta`。

验证基线（重构后应保持不劣化）：`backend` 下 `uv run pytest tests\test_benchmark_*.py tests\test_chat_stream_contract.py` 全绿；`--suite smoke --offline --fail-under 0.9` 4/4 通过、退出 0；前端 `npm run test` 4/4 通过。

## 改进计划 Backlog

下面是 B5 之后的重构项。每项给出：问题（含代码锚点）→ 改动 → 影响文件 → 完成标准（DoD，含测试）。优先级 P1 = 会导致漏判/误判的正确性问题，P2 = 可维护性/配置化，P3 = 需要新层级或较大投入。

### B6 — gate 默认排除 negative fixture（P1）

- 问题：`select_cases`（`harness.py:152`）只按 `--suite` / `--case-id` / `--offline` 过滤，不识别 `negative` tag；裸 `--offline` 会把 `agent_basic.must_not_include_001` 这类预期失败的 scorer 验证 fixture 也选进来，无法直接当 gate。
- 改动：在 `select_cases` 增加默认排除 `negative` tag 的行为，并加 `--include-negative` 显式开关。
- 影响文件：`benchmarks/runners/harness.py`、`benchmarks/runners/run_benchmarks.py`（新增参数）、`benchmarks/README.md` 与本文运行命令说明。
- DoD：`--offline` 默认不再选中 `negative` case；`--include-negative --offline` 恢复旧行为；`test_benchmark_runner.py` 覆盖两条路径。

### B6a — 普通工具 / DB / RAG fixture 隔离（P1）

- 问题：smoke 文档承诺不依赖 MySQL，但普通工具实现会直接导入 `AsyncSessionLocal`，例如 `list_memories_tool`。当前 smoke case 没触发普通读写工具，所以风险未暴露；后续一旦加入真实工具调用 fixture，可能误连真实数据库或真实 RAG/vector store。
- 改动：为 smoke 工具执行增加明确隔离层。可选方案包括：为普通工具提供 fixture-backed fake tool、在 benchmark harness 中 patch 对应工具依赖、或把涉及真实 DB/RAG 的 case 放入 full/integration 层。
- 影响文件：`benchmarks/runners/harness.py`、相关工具 fixture、`benchmarks/cases/*.yaml`、必要时 `backend/app/agent/tools/*` 的可注入接缝。
- DoD：新增一个会调用普通读工具的离线 case，运行时不访问真实 MySQL/RAG；测试中能断言真实 `AsyncSessionLocal` 未被调用；文档明确 smoke 只允许 fixture-backed 工具副作用。

### B7 — `forbidden_execute` 按事件顺序判定（P1）

- 问题：`_score_tool_policy`（`score_cases.py:162`）用集合差集 `executed = ended - blocked` 判断执行，`_executed_tool_ids`（`score_cases.py:218`）也是集合运算。同名工具若“先 blocked、后又真正 executed”，会因集合去重被误判为安全。
- 改动：改为按 `tool_call_index` 或事件顺序逐次配对 `tool_start` / `waiting_confirmation` / `tool_end`，任一次真实执行即命中 `forbidden_execute`。
- 影响文件：`benchmarks/runners/score_cases.py`。
- DoD：新增 fixture「同名工具先拦后放」被正确判失败；`test_benchmark_scoring.py` 锁定该顺序语义。
- 备注：该项是安全误判风险，实际排期应与 B6a 并列最高优先，优先于 B6 的 CLI 便利性修正。

### B8 — 新增 `require_non_empty_response_before_done`（P2）

- 问题：`drive_sse_stream` 起手固定发空 `response` 帧，`require_response_before_done`（`score_cases.py:116`）因此恒被满足，无法证明模型产出了用户可见内容。
- 改动：在 `_score_event_contract` 增加 `require_non_empty_response_before_done`，仅统计非空 `response`（与 `first_non_empty_response_ms` 口径一致）。
- 影响文件：`benchmarks/runners/score_cases.py`、`benchmarks/schemas/case.schema.json`（`event_contract` 若收紧 schema）。
- DoD：只发空 response 的 case 该项判失败；至少一条 smoke case 采用新契约并通过。

### B9 — Scorer 权重移入 case/suite 配置（P2）

- 问题：权重硬编码在 `score_cases.py:44-60`（`chat_stream` / `tool_safety` / `skill_routing` 一组，其余一组），与「case/suite 决定评分权重」的设计不符，改权重必须改代码。
- 改动：把权重下沉到 suite 级配置（或 case `expect.weights` 覆盖），代码只读配置并保留缺省。
- 影响文件：`benchmarks/runners/score_cases.py`、`benchmarks/cases/*.yaml`、`benchmarks/schemas/case.schema.json`。
- DoD：删除代码内硬编码权重表；缺省行为与现状一致（baseline 分数不变）；`test_benchmark_scoring.py` 覆盖配置覆盖路径。
- 备注：顺带确认 `skill_routing` 归入哪组权重（当前落在工程契约组，原计划未分类），在配置里显式写清。

### B10 — schema 接入 `load_cases` 校验 + `tool_policy` 字段收紧（P2；含 P1 安全子项）

- 问题一（孤儿 schema）：`benchmarks/schemas/{case,result}.schema.json` 目前是孤儿——没有任何代码 import/校验（在 `benchmarks/*.py` 全量 grep `schema`/`jsonschema` 零命中）；`load_cases`（`harness.py:123`）用手写的 `validate_case`（`harness.py:137`）。两者会各自漂移。
- 问题二（拼错字段静默失效，安全隐患，P1）：`case.schema.json` 里 `tool_policy` 仅为 `{"type": "object"}`，且顶层与各层普遍 `additionalProperties: true`；而 `score_case` 只读白名单键 `allowed / forbidden_call / forbidden_execute / expect_blocked`（`score_cases.py:141-178`）。因此拼错或杜撰的键（例如把安全红线写成 `forbidden` 而非 `forbidden_execute`）会被 schema 与 scorer 双双静默忽略，case 仍判通过——安全断言形同虚设却毫无报错。新手指南第四节此前示例即用了错误的 `forbidden` 字段，已同步修正。
- 改动：二选一并写清——(a) 在 `load_cases` 用 `jsonschema` 对 `case.schema.json` 校验，`validate_case` 退化为快速必填检查或删除；或 (b) 明确将 schema 标注为「仅参考」，并在 CI/测试里加一致性检查防漂移。无论选哪个，都要把 `tool_policy` 的合法键收紧为白名单并置 `additionalProperties: false`（`expect` 内 `tool_policy` / `event_contract` 同理），让未知键校验期即报错。
- 影响文件：`benchmarks/runners/harness.py`、`benchmarks/schemas/*.json`、`backend` 依赖（若引入 `jsonschema`）。
- DoD：schema 与实际校验逻辑单一事实来源；所有现有 YAML case 通过 schema 校验；`tool_policy` 出现未知键（如 `forbidden`）时校验失败并给出可定位报错；新增测试锁定「未知 tool_policy 键 → 报错」与「schema 与加载校验不脱节」两条路径。
- 备注：问题二是安全断言静默失效风险，实际排期应与 B7 / B6a 并列最高优先；问题一（jsonschema 接线）可随后跟进。

### B11 — `.gitignore` EOL 收敛（P3）

- 问题：`.gitignore` 之前的改动混入 LF→CRLF 行尾翻转（约 7 行无关行），真正意图只是新增 `benchmarks/results/*` 与 `!.gitkeep` 两行。
- 改动：把无关的 EOL 翻转回退，只保留两行实质新增。
- 影响文件：`.gitignore`。
- DoD：`git diff` 仅显示 2 行实质变更，无行尾噪声。

### 更远层级（暂不排期）

- `skill_routing` 离线 case 只能覆盖显式 `tool_ids` 或确定性关键词路径；真实 embedding 语义路由属于 online/full 层，不进 smoke。
- 真实 RAG benchmark 必须使用固定 fixture，严禁读取真实用户知识库；需要时新建 full/integration 层，不改 smoke 的零依赖假设。

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
