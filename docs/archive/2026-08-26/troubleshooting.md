# 故障排除

先确认问题属于哪个进程，再按本页对应章节排查。不要同时重建虚拟环境、删除模型和清空数据；一次只改变一个变量。

## 快速诊断

从仓库根目录执行：

```powershell
# 端口
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object LocalPort -In 18000,18001,18020,18080,11434,3306 |
  Sort-Object LocalPort

# Python 环境
& .\backend\.venv\Scripts\python.exe --version
& .\DjangoUserService\.venv\Scripts\python.exe --version

# FastAPI
Invoke-RestMethod http://127.0.0.1:18000/health/live
Invoke-RestMethod http://127.0.0.1:18000/health/ready

# Django docs
Invoke-WebRequest http://127.0.0.1:18001/docs/ -UseBasicParsing
```

健康检查语义：

- `/health/live`：FastAPI 进程可响应。
- `/health/ready`：MySQL 和 Redis 可用。
- 两者都不检查 Ollama、Embedding、Reranker、Chroma 或 MCP。

## 启动顺序问题

推荐顺序：

```text
MySQL
Redis / Ollama
Django
FastAPI
Frontend
```

一键脚本会等待 Redis/Ollama、Django、FastAPI 和前端端口，但 MySQL 只检查并警告，不会自动启动。

脚本提示端口 ready 只表示 TCP 可连接，不代表模型后台预热完成。Reranker 或 Embedding 问题应继续查看 FastAPI 日志。

### ENV 或 DEBUG_MODE 导致启动失败

两个后端只接受 `dev/development`、`test/testing`、`prod/production`。`staging`、拼写错误或空值会直接失败，必须改为受支持的环境名，再通过独立配置区分部署。FastAPI 在 `prod/production` 下还要求显式设置 `DEBUG_MODE=false`；不要为了启动而把生产异常详情重新打开。

## Python 与 uv

### 找不到合适的 Python

当前仓库要求：

- FastAPI：Python 3.12。
- Django `.python-version`：Python 3.13。

项目设置了 `python-downloads = "never"`，uv 不会自动安装 Python。

```powershell
py -0p
uv python list
```

安装缺失版本后重新同步：

```powershell
cd backend
uv sync --extra dev

cd ..\DjangoUserService
uv sync
```

### uv cache 拒绝访问

先关闭占用 `.venv` 或 `.uv-cache` 的 Uvicorn、Django、测试和编辑器 Python 进程，再重试。不要在进程仍运行时删除虚拟环境。

```powershell
Get-Process python,uvicorn -ErrorAction SilentlyContinue
```

仍失败时检查目录 ACL、杀毒软件隔离和磁盘状态。管理员 PowerShell 只用于确认权限问题，不应作为日常运行要求。

### pytest 找不到

开发依赖是 optional extra：

```powershell
cd backend
uv sync --extra dev
uv run pytest
```

## Node 与前端

### 确认 npm 管理的 Node 环境

项目完整使用 npm 管理前端依赖和脚本。先确认当前终端解析到受支持的 Node 与配套 npm：

```powershell
Get-Command node -ErrorAction SilentlyContinue
Get-Command npm.cmd -ErrorAction SilentlyContinue
node --version
npm --version
```

仓库不要求 yarn 或 pnpm。一键脚本会额外检查常见的 nvm-windows 和 Program Files 路径；如果当前终端找不到命令，应修复 Node 安装或 PATH 后重新打开终端。

### Vite 报 Node 版本不支持

Vite 8 要求：

```text
^20.19.0 || >=22.12.0
```

升级 Node 后重建依赖：

```powershell
cd front
Remove-Item -Recurse -Force node_modules
npm ci
```

删除 `node_modules` 前确认当前目录是 `front`。不要删除 `package-lock.json` 来规避 engines 错误。

### 前端请求 404 或代理到错误服务

检查 `front/vite.config.ts`：

- `/user`、`/file` -> Django 18001。
- 业务 API -> FastAPI 18000。
- `/api/skills`、`/api/tools` 会移除 `/api`。

自定义后端端口时同时设置代理目标：

```powershell
$env:VITE_BACKEND_TARGET='http://127.0.0.1:19000'
$env:VITE_USER_TARGET='http://127.0.0.1:19001'
npm run dev
```

只修改 `start-all.ps1 -BackendPort` 不会自动修改 Vite proxy target。

### Vite 构建清理 dist 时出现 EPERM

症状：TypeScript 检查和模块转换已经完成，但 Vite 在 `prepare-out-dir` 阶段无法删除 `front/dist` 中的旧文件。

```text
Error: EPERM: operation not permitted, unlink '...front\dist\assets\...js'
```

这通常是旧产物被预览服务器、编辑器、资源管理器、杀毒软件或 ACL 占用，不是源代码编译错误。

排查：

1. 关闭 `vite preview`、静态文件服务器和可能读取 dist 的进程。
2. 检查报错文件的只读属性和目录权限。
3. 使用新输出目录区分构建问题与旧目录问题：

   ```powershell
   npm run build -- --outDir dist-build-check
   ```

4. 新目录构建成功后，再处理旧 `dist` 的占用或 ACL；确认目录后删除临时构建产物。

不要通过删除 `package-lock.json` 或修改 TypeScript 配置解决 `unlink EPERM`。

## MySQL

### 数据库连接失败

检查监听：

```powershell
Test-NetConnection 127.0.0.1 -Port 3306
```

确认两个 database 已创建：

```sql
SHOW DATABASES;
```

FastAPI 使用 `MYSQL_*` 和 `MYSQL_DATABASE`；Django 使用 `DB_*`。它们通常连接不同 database。

常见原因：

- MySQL 服务未启动。
- database 不存在。
- 用户没有目标 database 权限。
- 密码包含 URL 特殊字符，而 FastAPI 当前连接字符串未做 URL 编码。
- Django migration 尚未运行。

```powershell
cd DjangoUserService
uv run python manage.py migrate
```

### FastAPI 报数据库 revision 缺失或不匹配

FastAPI 启动只验证 `alembic_version`，不会创建表、补列或自动升级。如果是新空库，从 `backend` 显式执行：

```powershell
uv run alembic upgrade head
```

如果数据库已有业务表但没有 revision，不要直接 upgrade 或 stamp。先停止写入、完成备份，将实际 schema 与 `backend/alembic/versions/20260817_0001_baseline.py` 逐项核对；只有确认完全一致后，才可以执行：

```powershell
uv run alembic stamp 20260817_0001
```

`alembic stamp` 只记录版本，不会修复结构差异。核对 baseline 时必须包含 `uq_knowledge_source_user_md5` 和 `uq_user_embedding_config_user_id` 两个唯一约束。revision 落后时应审查待执行 migration，再运行 `uv run alembic upgrade head`；revision 超前或出现分叉时，应停止启动并核对部署的代码版本。

## Redis

默认端口是 18020，不是 Redis 常见的 6379：

```powershell
Test-NetConnection 127.0.0.1 -Port 18020
redis-cli -p 18020 ping
```

检查：

- FastAPI `REDIS_HOST/REDIS_PORT/REDIS_DB`。
- Django `REDIS_CACHE_URL`。
- Django Celery URL。

Redis 不可用会影响就绪检查、用户缓存、token 撤销、认证状态短缓存、限流和高风险 pending action。Django `REDIS_CACHE_URL` 与 FastAPI `JWT_REDIS_URL` 必须指向同一撤销存储；该存储异常时认证、refresh 或 logout 可能返回 `503`，这是 fail-closed 行为。

## Windows 端口绑定错误 10013

症状：

```text
An attempt was made to access a socket in a way forbidden by its access permissions
```

不要假定 18000、18001 或 18080 永远位于动态/保留范围之外。Windows 默认动态 TCP 范围通常是 49152-65535，但 WinNAT、Hyper-V、WSL2、Docker 或系统策略可能产生不同的动态区和 excluded ranges。

只读检查：

```powershell
netsh int ipv4 show dynamicport tcp
netsh interface ipv4 show excludedportrange protocol=tcp
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object LocalPort -In 18000,18001,18020,18080
```

处理顺序：

1. 确认不是已有进程占用。
2. 检查目标端口是否落入 excluded range。
3. 选择当前机器未监听且未保留的端口。
4. 同步修改启动端口、Vite proxy、`.env` 中的服务 URL 和 Redis URL。
5. 仅在理解 Docker/Hyper-V 影响时，使用管理员权限调整系统端口策略。

不要仅因为端口号“大于 15000”就判断安全。

## JWT 与登录

### FastAPI 返回 401

检查：

- 请求是否带 `Authorization: Bearer <access token>`，而不是 refresh token。
- Django `JWT_SECRET_KEY` 是否等于 FastAPI `SECRET_KEY`。
- 两端的 `ALGORITHM`、`JWT_ISSUER` 和 `JWT_AUDIENCE` 是否一致。
- token 是否包含 `token_type=access`、`jti`、`sid`、`ver` 和有效的时间声明。
- 默认 15 分钟的 access token 是否过期，或是否已在注销、资料更新、密码重置时撤销。
- Django 用户是否仍为 active，token version 是否仍匹配。

普通 Axios 请求会使用 refresh token 自动刷新一次并重试；刷新成功后 access/refresh token 都会轮换。直接 `fetch` 的 SSE 请求不经过 Axios 刷新拦截器，收到 `401` 后应重新登录或先通过普通请求完成刷新。不要通过关闭 token 验证解决配置问题。

### Refresh token 被拒绝或重复使用

refresh token 默认有效期 30 天，但每个 token 只能成功使用一次。成功刷新会撤销旧 refresh token 并返回新 token 对；并发请求由前端合并为一次刷新。如果自定义客户端并发提交同一个 refresh token，只有一个请求能成功，其余会返回 `401`。

旧版单 token 或缺少类型、issuer、audience、JTI 的 JWT 不再兼容，需要重新登录。

### 认证或刷新返回 503

`503` 表示服务无法确认撤销状态或用户状态，不等同于凭据无效。依次检查：

- Django `REDIS_CACHE_URL` 和 FastAPI `JWT_REDIS_URL` 对应的 Redis 是否可用。
- FastAPI 是否能访问 `DJANGO_API_URL`。
- Django 用户详情接口是否正常响应。
- 生产环境是否错误地禁用了 `AUTH_STATE_VALIDATION_ENABLED`。

恢复依赖后再重试。不要把 `503` 当作成功，也不要改成跳过撤销检查。

### 更新资料或密码后突然退出

资料更新和密码重置会撤销旧 access token 并返回新 access/refresh token 对；密码重置还会递增 token version。当前前端会同时保存两类新 token，自定义客户端也必须这样处理，否则下一次请求会进入刷新或重新登录流程。

## 聊天模型

### 阿里云 API Key 或模型错误

检查 `backend/.env`：

```env
LLM_TYPE=ALIYUN
ALIYUN_ACCESS_KEY_SECRET=...
ALIYUN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL_NAME=qwen3-max
```

代码兼容旧 `ALIYUN_MODEL_NAME`，新配置统一使用 `CHAT_MODEL_NAME`。

检查账户模型权限、余额、region 和网络。用户模型配置优先于系统默认；如果只在某个保存模型上失败，先在模型设置页运行连接测试。

### Ollama 连接失败

```powershell
Test-NetConnection 127.0.0.1 -Port 11434
ollama list
```

确认模型名称与本地列表完全一致。默认 Embedding 使用 Ollama，因此即使聊天使用阿里云，Ollama 未启动仍可能导致知识库初始化失败。

## Embedding 与 Chroma

### Embedding 模型不存在

默认：

```env
EMBED_MODEL_TYPE=OLLAMA
TEXT_EMBEDDING_MODEL_NAME=qwen3-embedding:0.6b
```

```powershell
ollama pull qwen3-embedding:0.6b
ollama list
```

### 切换 Embedding 后检索异常

不同 Embedding 产生的向量空间不兼容。切换模型后，已有文档可能需要重新索引。先确认当前模型接口和文档入库记录，再决定是否清理向量数据。

不要直接删除整个 `backend/data`；其中还可能包含源文件、MD5 记录和其他运行数据。

### Chroma 权限或损坏

默认目录：

```text
backend/data/chromadb
```

停止所有 FastAPI 进程后再检查文件锁、磁盘空间和目录权限。清理前备份 `backend/data`，并确认可以从源文件重建索引。

## Reranker

### 启动很慢

默认 `Qwen/Qwen3-Reranker-4B` 会在后台检查、下载和预热。Uvicorn 可先启动，模型日志稍后完成。

资源有限时切换到：

- `Qwen/Qwen3-Reranker-0.6B`。
- `BAAI/bge-reranker-v2-m3`。

### 模型目录存在但无法加载

检查是否缺少权重分片、index、tokenizer 或 sentence-transformers 配置。ModelScope 下载中断可能留下临时目录。

完整说明见 [本地 Reranker 配置](./modelscope_model.md)。

### CUDA / sm_120 不兼容

```powershell
cd backend
uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_arch_list() if torch.cuda.is_available() else [])"
```

重建 CUDA 13.2 环境：

```powershell
cd ..
powershell -ExecutionPolicy Bypass -File .\scripts\rebuild-backend-cu132.ps1
```

脚本会请求确认后删除 `backend/.venv`。关闭后端进程并阅读脚本输出后再执行。

## 文档上传

支持：`txt`、`pdf`、`md`、`pptx`、`docx`。

失败时检查：

- JWT 是否有效。
- 文件类型是否在 `config/chroma.yaml` 中。
- `backend/data` 是否可写。
- 文档解析依赖是否安装完整。
- PDF 视觉处理所需模型是否可用。
- FastAPI 日志中的解析阶段错误。

头像上传属于 Django `/file/upload/`，只支持 jpg/jpeg/png/gif 且最大 1 MiB，与知识库上传不是同一接口。

## MCP

### stdio server 找不到 mcp 包

`command: python` 按 FastAPI 进程 PATH 查找独立子进程解释器，可能不是 `backend/.venv`。

```powershell
cd backend
uv run python -c "import sys, mcp; print(sys.executable); print(mcp.__file__)"
```

处理：

- 使用 `uv run uvicorn ...` 启动 FastAPI。
- 确保子进程 PATH 指向包含 mcp 的环境。
- 本机调试可把 command 改为明确 venv Python，但不要提交机器专用绝对路径。

### server 显示 error

读取：

```http
GET /api/mcp/servers
```

检查 `last_error`、transport、command/url、allow/deny 和 server 日志。管理员可以调用 refresh；普通用户无权刷新。

```http
POST /api/mcp/servers/refresh
```

refresh 证明 `tools/list` 成功，不代表每个工具调用都成功。当前没有独立 test endpoint。

### 修改 MCP 后找不到配置差异

这是历史本地开发说明：当前 `mcp.local.yaml` 只作为默认只读的 discovery adapter/cache，不能作为策略或授权权威。管理 API/UI 在版本化 policy authority 未就绪时 fail-closed；只有显式 `MCP_ALLOW_LOCAL_CONFIG_WRITES=true`、`MCP_CONFIG_PATH` 和隔离维护流程才允许写入本地 YAML，且不得提交本机 URL、命令或 secret。

## Agent SSE

### 页面只有空消息或 thinking 顺序错乱

后端会先发送空 `response` 帧。前端应使用 `features/chat/hooks/useChatStream.ts`，并在 thinking、waiting_confirmation、error、done 前 flush response buffer。

验证：

```powershell
cd front
npm run test
```

### 回答中出现 HyDE 或摘要文本

`event_pump.py` 会屏蔽工具执行区间内的模型 token。如果出现中间产物，检查 tool start/end 深度是否失衡，以及供应商事件顺序是否与 `astream_events(version="v2")` 合同一致。

### 高风险操作停在确认状态

检查：

- Redis 是否可用。
- pending action 是否超过 600 秒 TTL。
- 确认请求是否使用同一用户 token。
- `pending_action_id` 是否已被消费。

不存在、过期、重复或越权的确认统一返回 410。重新发起原请求生成新的 pending action。

### 运行到 1200 秒被停止

默认 `max_runtime_seconds=1200`。SSE driver 会取消 Agent，保留部分文本并落库停止说明。优先缩小任务范围，而不是无限提高预算。

## Benchmark

日常 gate：

```powershell
cd backend
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

裸 `--offline` 默认排除 negative fixtures。需要验证 scorer 失败路径时显式添加：

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --offline --include-negative
```

运行结果位于 `benchmarks/results/`。

## 日志位置

FastAPI 日志默认位于：

```text
backend/logs/
```

同时检查启动终端，因为模型下载、Uvicorn、Django 和 MCP 子进程错误可能直接输出到控制台。

排查时记录：

- 失败服务和 endpoint。
- HTTP status 或完整异常首尾。
- Python、Node、uv 和关键依赖版本。
- 相关端口监听状态。
- 使用的模型 provider 和 model name。
- 是否可稳定复现。

不要在问题报告中粘贴 API key、JWT、数据库密码、完整用户数据或 MCP secret。
