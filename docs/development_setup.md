# Doki助手开发与运行说明

本文记录 Doki助手的本地开发、启动、配置和验证方式。项目展示页见 [README](../README.md)。

## 本地启动

### 后端

```powershell
cd backend
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 前端

```powershell
cd front
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

### 用户服务

```powershell
cd DjangoUserService
uv sync
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8001
```

### Windows 一键启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

访问地址：

- 前端：<http://127.0.0.1:3000>
- FastAPI 文档：<http://127.0.0.1:8000/docs>
- Django 文档：<http://127.0.0.1:8001/docs/>

## 关键配置

管理员名单：

```text
backend/app/config/security.yaml
```

Agent 运行预算：

```text
backend/app/config/agent.yaml
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
TEXT_EMBEDDING_MODEL_NAME=qwen3-embedding:0.6b

MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=chat_history

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

DJANGO_API_URL=http://127.0.0.1:8001

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
| Agent | LangChain、Tool Calling、Skill/Tool Registry |
| RAG | ChromaDB、Ollama Embedding、CrossEncoder Reranker |
| 模型 | 阿里云百炼、OpenAI-compatible API、Ollama |

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
