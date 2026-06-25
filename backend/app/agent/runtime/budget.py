from pathlib import Path

import yaml


DEFAULT_RUNTIME_BUDGET = {
    "max_iterations": 160,
    "max_tool_calls": 120,
    "max_runtime_seconds": 1200,
    "max_output_chars_per_tool": 16000,
}


def get_runtime_budget() -> dict:
    config_path = Path(__file__).parents[2] / "config" / "agent.yaml"
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    runtime = data.get("runtime") if isinstance(data, dict) else {}
    if not isinstance(runtime, dict):
        runtime = {}
    budget = DEFAULT_RUNTIME_BUDGET.copy()
    for key, default in DEFAULT_RUNTIME_BUDGET.items():
        value = runtime.get(key)
        if isinstance(value, int) and value > 0:
            budget[key] = value
        else:
            budget[key] = default
    return budget
