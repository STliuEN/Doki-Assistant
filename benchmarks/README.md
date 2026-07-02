# Benchmarks

This directory contains the local benchmark harness for the assistant runtime.

The first supported layer is `smoke`: offline, scripted, no real model, no MySQL,
no embedding service, and no MCP discovery. It exercises the production stream
path by injecting a fake agent factory into `get_agent_stream_response`.

## Run

Run the smoke gate from the backend directory:

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

Run the related backend tests:

```powershell
uv run pytest tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_chat_stream_contract.py
```

Use `--case-id` while developing one fixture:

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --case-id agent_basic.plain_text_001 --offline
```

Do not use bare `--offline` as a pass/fail gate. It also selects intentionally
failing negative fixtures such as `agent_basic.must_not_include_001`, which are
kept to test the scorer itself. Gate normal development with `--suite smoke`.

## Case Notes

- `tags: [smoke, ...]` marks cases that should pass in the local smoke gate.
- `tags: [negative, ...]` marks scorer verification fixtures that are expected
  to fail and should not be included in the smoke gate.
- `tool_safety` cases distinguish a tool being called from a tool being
  executed. A high-risk tool may be attempted, but it must emit
  `waiting_confirmation` and must not perform the underlying action.
- The SSE driver begins streams with an empty `response` frame. Latency and
  response-contract checks should use the first non-empty response when they
  are meant to prove user-visible content was produced.

Generated files go under `benchmarks/results/` and are ignored except for
`.gitkeep`.
