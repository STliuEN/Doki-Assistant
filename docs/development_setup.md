# 开发与运行说明

本文是 Doki 助手本地开发环境的操作基线。架构说明见 [当前架构](./project_develop.md)，常见故障见 [故障排除](./troubleshooting.md)。

## 运行组成

本地开发需要三个应用进程和外部基础设施：

| 组件 | 默认地址 | 是否必需 |
|------|----------|----------|
| React/Vite | `127.0.0.1:18080` | 是 |
| FastAPI | `127.0.0.1:18000` | 是 |
| DjangoUserService | `127.0.0.1:18001` | 是 |
| MySQL | `127.0.0.1:3306` | 是 |
| Redis | `127.0.0.1:18020` | 是 |
| Ollama | `127.0.0.1:11434` | 使用 Ollama 聊天模型或本地 Embedding 时需要 |

FastAPI 启动时会创建缺失的业务表和列，但不会创建 MySQL database。Django 的表由 migration 管理。

## 工具链版本

### Python

- `backend/.python-version` 是 `3.12`。
- `backend/pyproject.toml` 严格要求 `>=3.12,<3.13`。
- `DjangoUserService/.python-version` 是 `3.13`。
- `DjangoUserService/pyproject.toml` 声明支持 `>=3.10`。

两个项目都配置了 `python-downloads = "never"`，所以 `uv` 不会自动下载 Python。建议直接安装 Python 3.12 和 3.13，与仓库固定版本保持一致。

### Node.js

前端使用 Vite 8。其 engines 要求：

```text
^20.19.0 || >=22.12.0
```

Node.js 18 不满足当前前端依赖要求。

### 基础设施

- MySQL 8.x。
- Redis 7.x。
- 可选 Ollama，用于本地聊天模型和默认的 Ollama Embedding。

## 首次初始化

以下命令均从仓库根目录开始。

### 1. 创建 MySQL database

```sql
CREATE DATABASE chat_history CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE user_service CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

名称可以修改，但必须与两个 `.env` 中的配置一致。

### 2. 创建本地配置

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item DjangoUserService\.env.example DjangoUserService\.env
.\scripts\migrate-local-config.ps1
```

迁移脚本会创建 Git 忽略的 `security.local.yaml` 和 `mcp.local.yaml`。已有 `.env` 若尚未声明 `MODEL_CONFIG_ENCRYPTION_KEY`，脚本会先复制当前 `SECRET_KEY` 的值，以保证已有模型 API key 密文仍可解密。

不要提交 `.env` 或 `*.local.yaml`。仓库的 `.gitignore` 已忽略这些文件。

### 3. 配置 FastAPI

以 `backend/.env.example` 为完整字段清单。最小关注项：

```env
# 聊天模型
LLM_TYPE=ALIYUN
ALIYUN_ACCESS_KEY_SECRET=your_api_key
ALIYUN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL_NAME=qwen3-max

# 或本地 Ollama 聊天模型
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=qwen3:0.6b

# Embedding
EMBED_MODEL_TYPE=OLLAMA
TEXT_EMBEDDING_MODEL_NAME=qwen3-embedding:0.6b

# MySQL
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=chat_history

# Redis
REDIS_HOST=localhost
REDIS_PORT=18020
REDIS_DB=0

# Django 与 JWT
DJANGO_API_URL=http://127.0.0.1:18001
SECRET_KEY=replace_with_a_shared_secret
MODEL_CONFIG_ENCRYPTION_KEY=replace_with_a_model_config_secret
ALGORITHM=HS256
```

新安装可以直接使用独立的模型配置加密密钥。已有密文需要分离密钥时，先设置 `MODEL_CONFIG_ENCRYPTION_KEY_PREVIOUS`，执行 `uv run python scripts\rotate_model_config_keys.py` dry-run，确认数量后再加 `--apply`；迁移完成后删除 previous key。

当 `ENV` 不是开发或测试环境时，FastAPI 会在启动阶段拒绝空值、示例值、少于 32 字符或彼此相同的 `SECRET_KEY` 和 `MODEL_CONFIG_ENCRYPTION_KEY`。

代码同时兼容旧变量 `ALIYUN_MODEL_NAME`，但新配置应统一使用模板中的 `CHAT_MODEL_NAME`。

默认 Reranker 配置是 `Qwen/Qwen3-Reranker-4B`，会占用较多磁盘、内存和显存。配置与替代方案见 [本地模型配置](./modelscope_model.md)。

### 4. 配置 Django

```env
JWT_SECRET_KEY=replace_with_a_shared_secret

DB_ENGINE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=user_service
DB_USER=root
DB_PASSWORD=root

CELERY_BROKER_URL=redis://localhost:18020/0
CELERY_RESULT_BACKEND=redis://localhost:18020/0
REDIS_CACHE_URL=redis://localhost:18020/1
```

`JWT_SECRET_KEY` 必须与 FastAPI 的 `SECRET_KEY` 完全一致。Django 生成的 JWT 固定使用 HS256，当前有效期为 24 小时。

### 5. 安装依赖与迁移

```powershell
cd backend
uv sync --extra dev

cd ..\DjangoUserService
uv sync
uv run python manage.py migrate

cd ..\front
npm ci
```

日常只运行应用、不运行后端测试时，后端可以使用 `uv sync`；开发环境使用 `--extra dev` 安装 pytest、ruff 等工具。

## 启动方式

### Windows 一键启动

```powershell
.\start-all.bat
```

等价命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

常用参数：

| 参数 | 作用 |
|------|------|
| `-Mode Terminal` | 默认，在同一 Windows Terminal 窗口中创建多个 Tab |
| `-Mode Window` | 每个服务使用独立 PowerShell 窗口 |
| `-SkipRedis` | 不启动 Redis |
| `-SkipOllama` | 不启动 Ollama |
| `-SkipFrontend` | 不启动前端 |
| `-SkipBackend` | 不启动 FastAPI |
| `-SkipUserService` | 不启动 Django |
| `-NoReload` | FastAPI 不启用热重载 |
| `-WaitTimeoutSeconds 120` | 调整每个服务的端口等待时间 |

脚本只检查 MySQL 是否可连接，不会启动 MySQL。Redis 和 Ollama 只有在命令存在且端口未监听时才会自动启动。

### VS Code Tasks

打开 `Terminal -> Run Task`，选择 `doki: start all`。任务定义位于 `.vscode/tasks.json`，同样按 Redis、Ollama、Django、FastAPI、前端的顺序启动。

### 手动启动

分别打开终端：

```powershell
# Django
cd DjangoUserService
uv run python manage.py runserver 127.0.0.1:18001
```

```powershell
# FastAPI
cd backend
uv run uvicorn main:app --host 127.0.0.1 --port 18000 --reload
```

```powershell
# Frontend
cd front
npm run dev -- --host 127.0.0.1 --port 18080
```

## 访问与健康检查

- 前端：<http://127.0.0.1:18080>
- FastAPI OpenAPI：<http://127.0.0.1:18000/docs>
- Django Swagger：<http://127.0.0.1:18001/docs/>
- FastAPI 存活：<http://127.0.0.1:18000/health/live>
- FastAPI 就绪：<http://127.0.0.1:18000/health/ready>

`/health/live` 只说明应用进程存活；`/health/ready` 会检查 MySQL 和 Redis，不检查 Ollama、Embedding、Reranker 或 MCP server。

## 前端代理

Vite 默认代理目标：

```text
FastAPI: http://127.0.0.1:18000
Django:  http://127.0.0.1:18001
```

可在启动前覆盖：

```powershell
$env:VITE_BACKEND_TARGET='http://127.0.0.1:18000'
$env:VITE_USER_TARGET='http://127.0.0.1:18001'
npm run dev
```

`/user` 和 `/file` 转发到 Django；聊天、知识库、笔记、记忆、模型配置、翻译及 `/api/mcp` 转发到 FastAPI。`/api/skills` 与 `/api/tools` 会去掉 `/api` 前缀后转发。

## 有效配置文件

| 文件 | 当前用途 |
|------|----------|
| `backend/app/config/agent.yaml` | Agent 最大迭代、工具调用、运行时间和输出预算 |
| `backend/app/config/chroma.yaml` | Chroma collection、持久化目录、切片和文件类型 |
| `backend/app/config/mcp.example.yaml` | 受版本控制的 MCP 示例；所有 server 默认禁用 |
| `backend/app/config/mcp.local.yaml` | 本机 MCP server、allow/deny 和 tool override；Git 忽略 |
| `backend/app/config/prompt.yaml` | Prompt 名称到文件的映射 |
| `backend/app/config/security.example.yaml` | 受版本控制的管理员配置模板，不含个人身份 |
| `backend/app/config/security.local.yaml` | 本机管理员兜底名单；Git 忽略 |
| `backend/app/config/rag.yaml` | 仅保留迁移说明，不再生效 |

通过 ToolManager 修改 MCP server/tool 会写回 `mcp.local.yaml`。首次修改时，后端会从 `mcp.example.yaml` 创建本机副本；本机 URL、命令和凭据不会进入 Git。

## 依赖维护

`pyproject.toml` 是 Python 直接依赖的来源，`uv.lock` 是可复现环境的锁文件，`requirements.txt` 是兼容 pip 的导出结果。

更新后端依赖：

```powershell
cd backend
uv lock
uv sync --extra dev
cd ..
.\scripts\export-requirements.ps1
```

更新 Django 依赖：

```powershell
cd DjangoUserService
uv lock
uv sync
cd ..
.\scripts\export-requirements.ps1
```

`requirements.txt` 是生成文件，禁止手工编辑。只读漂移检查使用 `.\scripts\export-requirements.ps1 -Check`。

更新前端依赖后必须提交 `package.json` 和 `package-lock.json`，干净环境使用 `npm ci` 验证。

## 验证命令

### 后端

```powershell
cd backend
uv run pytest -p no:cacheprovider
uv run ruff check main.py app tests scripts
uv run python scripts\export_openapi.py --check
```

当前测试覆盖 Agent 运行准备、运行时预算、意图路由、Benchmark runner/scorer 和 SSE 合同。

### Benchmark

```powershell
cd backend
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

裸 `--offline` 默认排除 `negative` fixtures，但范围比 `smoke` suite 更广。只有显式传入 `--include-negative` 才运行用于验证 scorer 失败路径的 negative fixtures。

### 前端

```powershell
cd front
npm run test
npm run build
npm run lint
```

前端测试重点覆盖 `useChatStream` 的 SSE 分包、事件 flush、重新生成覆盖和 `done.session_id`。

## 生产边界

当前 Django 使用 `DEBUG=True` 和宽松 CORS，FastAPI 也允许所有来源。仓库没有生产反向代理、TLS、静态资源部署、进程守护、数据库 migration 策略或 secret manager 配置。部署到公网前必须单独完成这些工作，不能直接复用开发启动命令。
