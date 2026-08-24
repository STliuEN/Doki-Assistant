# 开发与运行说明

本文是 `ARCH-GATE` 前 Doki 助手本地开发环境的操作基线。当前架构见[当前架构](./project_develop.md)，架构重写入口见[架构重写计划](./architecture_rewrite_plan.md)，当前最高优先级的 Skill 重构见[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)，常见故障见[故障排除](./troubleshooting.md)。

## 运行组成

本地开发当前需要三个应用进程和外部基础设施。三进程启动方式是过渡基线；架构重写完成后，启动方式以 `AR-6` 的单一入口 runbook 为准。

| 组件 | 默认地址 | 是否必需 |
|------|----------|----------|
| React/Vite | `127.0.0.1:18080` | 是 |
| FastAPI | `127.0.0.1:18000` | 是 |
| DjangoUserService | `127.0.0.1:18001` | 是 |
| MySQL | `127.0.0.1:3306` | 是 |
| Redis | `127.0.0.1:18020` | 是 |
| Ollama | `127.0.0.1:11434` | 使用 Ollama 聊天模型或本地 Embedding 时需要 |

应用启动不会创建 database、表或列，也不会生成或执行 migration、创建开发账号。Django schema 由已提交的 migration 管理；FastAPI schema 由 Alembic 管理，启动时只校验数据库 revision，不匹配时直接失败。架构重写阶段不会自动连接、迁移或删除现有 MySQL；数据接管必须遵循 [架构重写计划](./architecture_rewrite_plan.md) 的备份、dry-run、对账和恢复门禁。

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

前端完整使用 npm 管理依赖和脚本，`package-lock.json` 是锁文件；本地安装、测试、构建都使用 `npm`，不需要额外的包管理器。

### 基础设施

- MySQL 8.x。
- Redis 7.x。
- 可选 Ollama，用于本地聊天模型和默认的 Ollama Embedding。

## 首次初始化

以下命令均从仓库根目录开始，适用于当前过渡运行方式。

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
# 运行环境与浏览器来源
ENV=dev
DEBUG_MODE=true
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

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
JWT_REDIS_URL=redis://localhost:18020/1

# Django 与 JWT
DJANGO_API_URL=http://127.0.0.1:18001
SECRET_KEY=replace_with_a_shared_secret
MODEL_CONFIG_ENCRYPTION_KEY=replace_with_a_model_config_secret
ALGORITHM=HS256
JWT_ISSUER=doki-user-service
JWT_AUDIENCE=doki-api
AUTH_STATE_VALIDATION_ENABLED=true
```

新安装可以直接使用独立的模型配置加密密钥。已有密文需要分离密钥时，先设置 `MODEL_CONFIG_ENCRYPTION_KEY_PREVIOUS`，执行 `uv run python scripts\rotate_model_config_keys.py` dry-run，确认数量后再加 `--apply`；迁移完成后删除 previous key。

`ENV` 只接受 `dev/development`、`test/testing`、`prod/production`，拼写错误或其他值会拒绝启动。FastAPI 在 `prod/production` 下要求显式 `DEBUG_MODE=false`，并拒绝空值、示例值、少于 32 字符或彼此相同的 `SECRET_KEY` 和 `MODEL_CONFIG_ENCRYPTION_KEY`；同时要求显式配置 `JWT_REDIS_URL`、启用 `AUTH_STATE_VALIDATION_ENABLED`。生产环境的 `CORS_ALLOWED_ORIGINS` 必须是非空 allowlist，不能包含 `*`。

代码同时兼容旧变量 `ALIYUN_MODEL_NAME`，但新配置应统一使用模板中的 `CHAT_MODEL_NAME`。

默认 Reranker 配置是 `Qwen/Qwen3-Reranker-4B`，会占用较多磁盘、内存和显存。配置与替代方案见 [本地模型配置](./modelscope_model.md)。

### 4. 配置 Django

```env
ENV=dev
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOW_ALL_ORIGINS=false
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

JWT_SECRET_KEY=replace_with_a_shared_secret_at_least_32_characters
ALGORITHM=HS256
JWT_ISSUER=doki-user-service
JWT_AUDIENCE=doki-api
JWT_ACCESS_TTL_SECONDS=900
JWT_REFRESH_TTL_SECONDS=2592000

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

`JWT_SECRET_KEY` 必须与 FastAPI 的 `SECRET_KEY` 完全一致，issuer、audience 和撤销 Redis 也必须对齐。默认 access token 有效期为 900 秒，refresh token 有效期为 2592000 秒；refresh token 成功使用后会原子失效并轮换为一组新 token，不能重放。

两端使用同一组 `ENV` 枚举；未知值会拒绝启动。Django 生产环境会拒绝弱密钥、`DJANGO_DEBUG=true`、空的 allowed hosts/CORS allowlist、通配 CORS 和缺失的 `REDIS_CACHE_URL`。撤销存储不可用时，受保护接口、refresh 和 logout 采用 fail closed，返回 `503`，不会跳过检查。

### 5. 安装依赖与迁移

```powershell
cd backend
uv sync --extra dev
uv run alembic upgrade head

cd ..\DjangoUserService
uv sync
uv run python manage.py migrate

cd ..\front
npm ci
```

`alembic upgrade head` 只适用于新空库或已经纳入 Alembic 管理的数据库。接管已有但没有 `alembic_version` 的数据库前，必须先备份并将实际 schema 与 baseline 逐项核对；只有确认完全一致后才能执行 `alembic stamp 20260817_0001`，不能用 stamp 绕过结构差异。

日常只运行应用、不运行后端测试时，后端可以使用 `uv sync`；开发环境使用 `--extra dev` 安装 pytest、ruff 等工具。Web 启动命令不会代替上述 migration。

需要固定开发账号时，使用显式管理命令并传入仅供本机使用的密码：

```powershell
cd DjangoUserService
uv run python manage.py seed_dev_user --username dev --email dev@example.invalid --password '<local-only-password>'
```

该命令在 `ENV=prod` 或 `ENV=production` 时拒绝执行。正常注册流程不需要 seed。

## 启动方式（过渡基线）

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

一键脚本同样不会运行 migration 或创建账号。FastAPI 若报告 Alembic revision 缺失或不匹配，应先停止启动流程，按“首次初始化”中的数据库边界处理。

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
uv run alembic heads
uv run alembic upgrade head --sql
```

当前测试覆盖 Agent 运行准备、运行时预算、意图路由、Benchmark runner/scorer 和 SSE 合同。

### Django

Django 测试使用隔离的 SQLite 内存数据库；`ENV=test` 会强制使用 `LocMemCache`，不会连接本机 Redis：

```powershell
cd DjangoUserService
$env:ENV='test'
$env:SECRET_KEY='test-only-django-jwt-secret-at-least-32-characters'
$env:DB_ENGINE='sqlite3'
$env:DB_NAME=':memory:'
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
```

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

不能把 `start-all.ps1`、Django `runserver` 或 Vite dev server 作为生产启动方式。仓库已经具备生产配置的 fail-fast 基线：

- Django 要求强 JWT 密钥、`DEBUG=false`、显式 allowed hosts/CORS allowlist 和 Redis 撤销存储。
- FastAPI 要求分离的强 JWT/模型加密密钥、显式 CORS allowlist、`JWT_REDIS_URL` 和用户状态复核。
- 两个服务都拒绝生产通配 CORS；认证状态或撤销依赖不可确认时返回 `503`。
- Django migration 和 Alembic revision 均受版本控制，应用启动只验证，不修改 schema 或 seed 数据。

仍未交付的生产能力包括反向代理、TLS、静态资源部署、进程守护、secret manager、备份与回滚 runbook，以及用户可配置模型/Embedding 地址的 egress policy。完成这些部署层能力前，不应直接向公网开放。

具体风险和验收见 [安全与可靠性加固计划](./security_hardening_plan.md)，架构重写与 `ARCH-GATE` 见 [架构重写计划](./architecture_rewrite_plan.md)，R0-R8 追踪见 [全量重构开发计划](./roadmap_next.md)。只有安全计划中的“公网就绪条件”全部满足后，才能新增生产部署说明或放宽本节限制。
