# Benchmarks

This directory contains the local benchmark harness for the assistant runtime.

The default supported layer is offline: scripted model, no real MySQL, no
embedding service, and no MCP discovery. It exercises the production stream
path by injecting a fake agent factory into `get_agent_stream_response`.

The repository currently contains 121 passing offline cases: the four-case
`smoke` gate plus a 117-case `regression` matrix covering expression boundaries,
Skill/Tool assembly, high-risk confirmation, SSE, context settings, and error
recovery. One intentionally failing negative case verifies scorer behavior.

## Run

Run the smoke gate from the backend directory:

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

Run the related backend tests:

```powershell
uv run pytest tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_chat_stream_contract.py
```

Run the complete deterministic regression layer:

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --mode offline --tag regression --fail-on-veto
```

Use `--case-id` while developing one fixture:

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --case-id agent_basic.plain_text_001 --offline
```

Bare `--offline` excludes negative fixtures by default, but its selection is
still broader than the smoke gate. Gate normal development with `--suite smoke`.
Intentionally failing negative fixtures such as `agent_basic.must_not_include_001`
are kept to test the scorer itself and only run when `--include-negative` is
passed.

Run scorer negative fixtures explicitly when changing scoring behavior:

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --offline --include-negative
```

## Case Notes

- `tags: [smoke, ...]` marks cases that should pass in the local smoke gate.
- `tags: [negative, ...]` marks scorer verification fixtures that are expected
  to fail and should not be included in the smoke gate.
- Suite-level scorer weights live in `suites.yaml`; a case may override them with
  `expect.weights` when it needs a different scoring emphasis.
- Cases are validated against `schemas/case.schema.json` at load time. Unknown
  `expect.tool_policy` or `expect.event_contract` keys fail fast instead of
  being ignored by the scorer.
- `matrices` in a case YAML file expands strictly validated defaults plus rows
  into independent logical cases. Matrix IDs must remain unique repository-wide.
- `routing_contract`, `state_contract`, `efficiency_contract`, and enhanced
  `event_contract` fields protect actual prepared routes, side-effect counts,
  Tool budgets, ordering, unique events, and terminal events.
- `hard_vetoes` cannot be averaged away. Forbidden execution, cross-user access,
  or external access sets the case score to zero and adds a `*_veto` flag.
- `tags: [scripted_route]` fixes the route result to test downstream assembly;
  `tags: [production_route]` executes the production keyword router.
- `tool_safety` cases distinguish a tool being called from a tool being
  executed. A high-risk tool may be attempted, but it must emit
  `waiting_confirmation` and must not perform the underlying action.
- The SSE driver begins streams with an empty `response` frame. Latency and
  response-contract checks should use `require_non_empty_response_before_done`
  when they are meant to prove user-visible content was produced.
- Smoke cases that execute ordinary DB/RAG-adjacent tools must use fixture-backed
  tool data, for example `fixtures.tool_data.memories`; they must not reach
  real MySQL, vector stores, or user data.

Generated files go under `benchmarks/results/` and are ignored except for
`.gitkeep`.
