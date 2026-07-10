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

### npm 或 node 不在 PATH

```powershell
Get-Command node -ErrorAction SilentlyContinue
Get-Command npm.cmd -ErrorAction SilentlyContinue
```

一键脚本会额外检查常见的 nvm-windows 和 Program Files 路径，但手动运行仍需要正确 PATH。

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

### FastAPI 启动时自动补列失败

FastAPI 当前会在启动时 `create_all` 并执行自定义缺列迁移。检查 MySQL 用户是否有 `CREATE` 和 `ALTER` 权限，并查看日志中的 `[migrate]` SQL。

生产环境不应依赖该机制；正式 migration 仍在路线图中。

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

Redis 不可用会影响就绪检查、用户缓存、token 黑名单、限流和高风险 pending action。

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

- 请求是否带 `Authorization: Bearer <token>`。
- Django `JWT_SECRET_KEY` 是否等于 FastAPI `SECRET_KEY`。
- FastAPI `ALGORITHM=HS256`。
- token 是否超过 24 小时。
- token 是否已在注销、修改资料或重置密码时加入黑名单。

可以在 Django 重新登录获得新 token。不要通过关闭 token 验证解决配置问题。

### 更新资料或密码后突然退出

这是当前合同：更新资料和重置密码会撤销旧 token，并在响应返回新 token。前端或 API 客户端必须保存新 token。

### 注销未携带 token 仍返回成功

当前 Django 注销视图没有显式 `IsAuthenticated`，无 Authorization 时可能返回成功，但不会撤销任何 token。正常调用必须携带当前 token。该接口需要后续代码修复，不是安全保证。

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

### 修改 MCP 后 Git 出现配置差异

这是当前设计：ToolManager 的修改会写回 `backend/app/config/mcp.yaml`。提交前审查 diff，移除本机 URL、命令和 secret。

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
