# Benchmark 大规模扩展测试记录

日期：2026-07-11 ｜ 环境：Windows、Python 3.12.3

## 基线

执行：

```powershell
cd backend
uv run pytest tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_chat_stream_contract.py
```

结果：`18 passed`。

前端基线命令因当前终端没有可用 `npm` 而未执行；本次变更没有修改前端代码。

## 专项验证

### Runner、Scorer 与 AgentRunPlan

```powershell
uv run pytest tests\test_agent_run_service.py tests\test_benchmark_runner.py tests\test_benchmark_scoring.py
```

结果：`34 passed`。

### GuardedTool 与 Pending Action

```powershell
uv run pytest tests\test_tool_guard.py tests\test_pending_action_store.py
```

结果：`11 passed`。

### Benchmark 核心专项合集

```powershell
uv run pytest tests\test_benchmark_reporting.py tests\test_benchmark_runner.py tests\test_benchmark_scoring.py tests\test_tool_guard.py tests\test_pending_action_store.py
```

结果：`43 passed`。

## 最终验证

### 后端全量测试

```powershell
cd backend
uv run pytest
```

结果：最终为 `82 passed`（加入 offline socket 阻断回归测试后复跑）。

### Python 静态检查

```powershell
uv run ruff check main.py app tests scripts
```

结果：`All checks passed!`。

### Offline smoke

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

结果：4 个 case 全部通过，得分均为 `1.0`。

### Offline regression

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --mode offline --tag regression --fail-on-veto
```

结果：117 个 case 全部通过，得分均为 `1.0`，hard veto 为 `0`。

第一次完整 regression 运行发现 21 个 safety case 的 oracle 错把 `memory_cleanup` Skill 隐式带入的 Tool 当作异常。实际安全阻断、pending action 和副作用观测均正确。用例改为显式空 Skill + 精确 `delete_memory` Tool 后，安全子集 `21/21` 和完整 regression `117/117` 均通过。

### 文档与 Diff

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-docs.ps1
git diff --check
```

结果：Markdown 检查通过（113 个文件、50 个本地链接），`git diff --check` 无错误。Git 仅提示工作区换行符未来可能由 LF 转换为 CRLF，不属于内容错误。

## 未执行验证

- 前端 `npm run test` / `npm run build`：当前终端无 `npm`，且本次没有前端代码变更。
- Integration Benchmark：尚未建设专用 MySQL/Redis 测试环境。
- Online manual/auto 对照：未配置真实模型运行和版本化在线任务集。

未执行项没有伪造结果，继续作为后续里程碑保留。
