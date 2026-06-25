# Doki助手开发与运行说明

本文记录 Doki助手的本地开发、启动、配置和验证方式。项目展示页见 [README](../README.md)。

## 本地启动

### 后端

```powershell
cd backend
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 18000 --reload
```

### 前端

```powershell
cd front
npm install
npm run dev -- --host 0.0.0.0 --port 18080
```

### 用户服务

```powershell
cd DjangoUserService
uv sync
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:18001
```

### Windows 一键启动

支持两种启动模式，可按需选择。

模式①：单个 Windows Terminal 窗口、多 Tab（默认，最整洁）

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

模式①回退：每个服务一个独立 PowerShell 窗口（旧行为）

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1 -Mode Window
```

> 选 `Terminal` 但机器上没有 Windows Terminal（`wt.exe`）时，脚本会自动降级为 `Window` 模式。两种模式都保留阶梯启动：按 Redis/Ollama → Django → FastAPI → 前端 顺序逐个等待端口就绪再启动下一个。

模式②：VS Code 集成终端，零独立弹窗

在 VS Code 里打开命令面板或菜单 `Terminal → Run Task`，选择 `doki: start all`。所有服务在编辑器内的终端分组里按相同顺序启动，关闭 VS Code 即全部停止。配置见 `.vscode/tasks.json`。

访问地址：

- 前端：<http://127.0.0.1:18080>
- FastAPI 文档：<http://127.0.0.1:18000/docs>
- Django 文档：<http://127.0.0.1:18001/docs/>

> 端口统一使用 18000（后端）、18001（用户服务）、18080（前端），均在 Windows 动态端口区（1024–15000）之外，避免重启后被系统保留段占用导致 `bind: ...forbidden by its access permissions`（错误码 10013）。一键启动脚本 `scripts/start-all.ps1` 会按 Redis/Ollama → Django → FastAPI → 前端 的顺序逐个等待就绪再启动下一个，避免服务未就绪时的交叉调用失败。

## 关键配置

管理员名单：

```text
backend/app/config/security.yaml
```

Agent 运行预算：

```text
backend/app/config/agent.yaml
```

MCP 外部工具：

```text
backend/app/config/mcp.yaml
```

知识库与向量库：

```text
backend/app/config/chroma.yaml
backend/app/config/rag.yaml
```

Prompt 配置：

```text
backend/app/config/prompt.yaml
backend/app/prompt/
```

## 环境变量

### FastAPI 后端 `.env`

```env
LLM_TYPE=ALIYUN

ALIYUN_ACCESS_KEY_SECRET=your_api_key
ALIYUN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ALIYUN_MODEL_NAME=qwen3-max

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=qwen3:0.6b

EMBED_MODEL_TYPE=OLLAMA
TEXT_EMBEDDING_MODEL_NAME=qwen3-embedding:4b

MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=chat_history

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

DJANGO_API_URL=http://127.0.0.1:18001

SECRET_KEY=MY_JWT_SECRET_KEY
ALGORITHM=HS256

RERANKER_MODEL_PATH=./models/qwen3-reranker-4b
RERANKER_MODEL_NAME=Qwen/Qwen3-Reranker-4B
RERANKER_DEVICE=auto
RERANKER_MAX_LENGTH=8192
RERANKER_BATCH_SIZE=1
RERANKER_TORCH_DTYPE=auto
```

### Django 用户服务 `.env`

```env
JWT_SECRET_KEY=MY_JWT_SECRET_KEY

DB_PORT=3306
DB_NAME=user_service
DB_USER=root
DB_PASSWORD=root
DB_HOST=localhost

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

REDIS_CACHE_URL=redis://localhost:6379/1
```

FastAPI 和 Django 的 JWT 密钥、算法需要保持一致。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19、TypeScript、Vite、Tailwind CSS、Zustand、i18next |
| 后端 | FastAPI、SQLAlchemy、Redis、MySQL、ChromaDB |
| 用户服务 | Django、JWT、MySQL |
| Agent | LangChain、Tool Calling、Skill/Tool Registry、MCP SDK |
| RAG | ChromaDB、Ollama Embedding、CrossEncoder Reranker |
| 模型 | 阿里云百炼、OpenAI-compatible API、Ollama |

## 依赖重建

后端使用 `uv` 管理依赖。更新 `backend/pyproject.toml` 后，按下面顺序重建锁文件、同步虚拟环境，并更新兼容 `pip` 的 `requirements.txt`：

```powershell
cd backend
uv lock
uv sync
uv pip compile pyproject.toml -o requirements.txt
```

MCP 接入依赖当前包含：

```text
mcp==1.28.0
uvicorn==0.49.0
```

验证：

```powershell
cd backend
uv run python -c "from importlib.metadata import version; import uvicorn; print('mcp', version('mcp')); print('uvicorn', uvicorn.__version__)"
```

如果 Windows 上 `uv sync` 下载 `pywin32` 时出现 `.uv-cache` 拒绝访问，可用管理员权限 PowerShell 重新执行 `uv sync`。

## MCP 测试工具

最小 stdio MCP server 可放在：

```text
backend/mcp_servers/echo_server.py
```

示例：

```python
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


mcp = FastMCP("Doki Test MCP")


@mcp.tool(
    description="Echo a message back for MCP integration testing.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def echo(message: str) -> str:
    return f"echo: {message}"


if __name__ == "__main__":
    mcp.run("stdio")
```

配置 `backend/app/config/mcp.yaml`：

```yaml
servers:
  - id: doki_test
    label: Doki Test MCP
    enabled: true
    transport: stdio
    command: python
    args:
      - mcp_servers/echo_server.py
    allow_tools:
      - echo
    deny_tools: []
    default_risk_level: low
    default_requires_confirmation: false
    timeout_seconds: 10
    max_output_chars: 2000
```

刷新发现：

```powershell
cd backend
uv run python -c "import asyncio; from app.agent.mcp.registry import mcp_tool_registry; print(asyncio.run(mcp_tool_registry.refresh()))"
```

后端启动后也可以使用：

```text
POST /api/mcp/servers/refresh
GET  /api/mcp/tools
```

stdio MCP server 会作为子进程启动。`mcp.yaml` 中的 `command: python` 依赖当前 PATH 和启动方式；如果子进程使用了没有安装 `mcp` 包的系统 Python，会导致发现失败。开发和验证时优先使用：

```powershell
cd backend
uv run python -c "import asyncio; from app.agent.mcp.registry import mcp_tool_registry; print([t.to_public_dict() for t in asyncio.run(mcp_tool_registry.refresh())])"
```

如果必须直接用 venv Python 启动后端，请确认 stdio 子进程也能找到同一个环境，或在 `backend/app/config/mcp.yaml` 中把 `command` 改成明确的 venv Python 路径。

当前默认 smoke test server 为：

```text
backend/mcp_servers/powershell_ls_server.py
```

它只暴露只读 `list_project_files`，用于验证 MCP 发现、注册和调用链路。

## 开发检查

后端语法检查：

```powershell
python -m compileall backend\app
```

前端构建：

```powershell
cd front
npm run build
```

已知情况：前端构建可能提示 `tailwind.config.cjs` 的 ESM warning，但构建可以完成。
