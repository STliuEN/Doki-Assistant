# 本地 Reranker 配置

知识库在向量召回后可以使用本地 CrossEncoder 对候选片段重新排序。Reranker 不参与向量写入，因此切换模型不需要重建 Chroma 索引。

## 当前默认值

当前有效默认配置来自 `backend/app/services/reranker_config_service.py` 和 `backend/.env.example`：

```env
RERANKER_MODEL_PATH=./models/qwen3-reranker-4b
RERANKER_MODEL_NAME=Qwen/Qwen3-Reranker-4B
RERANKER_MODEL_REVISION=master
RERANKER_DEVICE=auto
RERANKER_MAX_LENGTH=8192
RERANKER_BATCH_SIZE=1
RERANKER_TORCH_DTYPE=auto
RERANKER_MIN_WEIGHT_MB=50
RERANKER_TRUST_REMOTE_CODE=false
```

旧文档中出现的 `BAAI/bge-reranker-v2-m3` 是仍受支持的轻量替代项，不是当前项目配置服务的默认值。

## 软件环境

以后端 `pyproject.toml` 为准：

- Python `>=3.12,<3.13`。
- `torch>=2.12.0`。
- `sentence-transformers>=5.3.0`。
- `transformers>=4.51.0`。
- `modelscope>=1.35.3`。

不要按旧说明使用 Python 3.8 或 sentence-transformers 2.x 创建当前后端环境。

安装由项目依赖统一管理：

```powershell
cd backend
uv sync --extra dev
```

不要单独执行 `uv add sentence-transformers torch`，除非确实要修改并提交项目依赖范围和 lock 文件。

## 模型选择

配置服务识别以下常用模型：

| 模型 | 建议场景 |
|------|----------|
| `Qwen/Qwen3-Reranker-4B` | 当前默认，质量优先，需要较多内存/显存 |
| `Qwen/Qwen3-Reranker-0.6B` | 本地资源有限、启动速度优先 |
| `BAAI/bge-reranker-v2-m3` | 多语言轻量替代 |

前端知识库页面可以读取本地模型目录并切换 Reranker。保存后的配置写入：

```text
backend/data/reranker_config.json
```

该运行数据被 `.gitignore` 忽略。优先级是：

1. `reranker_config.json` 中已保存的配置。
2. `backend/.env`。
3. 代码默认值。

因此修改 `.env` 后如果界面仍显示旧模型，应检查并删除或更新保存的运行时配置，而不是反复重装依赖。

## 自动下载和预热

FastAPI 启动后的后台初始化会创建 `ReorderService` 并执行 warmup：

1. 解析当前模型路径。
2. 检查目录和权重文件是否完整。
3. 不完整时清理 ModelScope 临时目录。
4. 使用 `modelscope.snapshot_download` 下载当前模型。
5. 使用 `sentence_transformers.CrossEncoder` 加载并预热。

模型目录至少需要模型配置、tokenizer 和一个完整权重文件。分片权重同样受支持。

Reranker 初始化失败不会阻止 FastAPI 进程监听；启动管理器会记录错误，检索链路跳过重排。Uvicorn 已启动不代表 Reranker 已就绪，应检查后端日志或知识库配置接口。

## 手动下载

自动下载不可用时，可从仓库根目录执行：

```powershell
uvx --from huggingface-hub hf download Qwen/Qwen3-Reranker-4B --local-dir .\backend\models\qwen3-reranker-4b
```

使用 Hugging Face 镜像：

```powershell
$env:HF_ENDPOINT='https://hf-mirror.com'
uvx --from huggingface-hub hf download Qwen/Qwen3-Reranker-4B --local-dir .\backend\models\qwen3-reranker-4b
```

不要复制旧仓库的绝对路径。`RERANKER_MODEL_PATH` 的相对路径以 `backend` 项目目录为基准解析。

常见的 Qwen3-4B 目录包含：

```text
backend/models/qwen3-reranker-4b/
  config.json
  modules.json
  config_sentence_transformers.json
  tokenizer.json
  tokenizer_config.json
  model-00001-of-00002.safetensors
  model-00002-of-00002.safetensors
  model.safetensors.index.json
  1_LogitScore/config.json
```

实际权重文件名可能随上游模型版本变化，代码通过 `model.safetensors`、`model-*.safetensors`、`pytorch_model.bin` 等模式检查。

## 字段语义

| 变量 | 说明 |
|------|------|
| `RERANKER_MODEL_PATH` | 本地保存目录；相对路径以 backend 为基准 |
| `RERANKER_MODEL_NAME` | ModelScope/Hugging Face 模型 ID |
| `RERANKER_MODEL_REVISION` | ModelScope revision |
| `RERANKER_DEVICE` | `auto`、`cpu`、`cuda` 等 torch device |
| `RERANKER_MAX_LENGTH` | CrossEncoder 最大输入长度 |
| `RERANKER_BATCH_SIZE` | predict 批大小 |
| `RERANKER_TORCH_DTYPE` | `auto`、`float16`、`bfloat16`、`float32` |
| `RERANKER_MIN_WEIGHT_MB` | 判断权重完整性的最小文件大小 |
| `RERANKER_TRUST_REMOTE_CODE` | 是否允许远程自定义代码；默认关闭 |

`RERANKER_TRUST_REMOTE_CODE=true` 会扩大模型代码执行边界，只应对经过审查的模型启用。

## Device 选择

`RERANKER_DEVICE=auto` 时：

1. 检查 CUDA 是否可用。
2. 检查当前 GPU compute capability 是否在 torch wheel 支持列表中。
3. 尝试在 CUDA 上创建 tensor。
4. 不满足时回退 CPU。

CPU 回退能保持功能可用，但 4B 模型加载和推理可能非常慢。资源不足时优先改用 0.6B 或 BGE 模型，而不是持续提高超时。

## RTX 50 / sm_120

后端 `pyproject.toml` 把 Windows torch 指向 CUDA 13.2 index。仓库提供重建脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rebuild-backend-cu132.ps1
```

脚本会：

- 检查默认 Qwen3-4B 模型文件，除非传 `-SkipModelCheck`。
- 请求确认后删除并重建 `backend/.venv`。
- 运行 `uv sync`。
- 输出 torch 版本、CUDA 可用状态和支持架构。

该脚本会删除虚拟环境，执行前应关闭正在使用它的后端进程。模型、MySQL 和 Chroma 数据不会被脚本删除。

只检查环境而不要求模型文件：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rebuild-backend-cu132.ps1 -SkipModelCheck
```

## 常见问题

### 下载中断

症状：模型目录存在，但缺少完整权重，或包含 `._____temp`、`.lock`。

处理：

- 停止重复启动的后端进程。
- 检查磁盘空间和网络。
- 重新启动，让服务清理不完整的 ModelScope 工作目录并下载。
- 或手动下载到新的完整目录，再切换配置。

### CUDA 不可用

```powershell
cd backend
uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_arch_list() if torch.cuda.is_available() else [])"
```

CUDA wheel、驱动和 GPU 架构必须同时兼容。代码会在不兼容时回退 CPU。

### 内存或显存不足

- 保持 `RERANKER_BATCH_SIZE=1`。
- 适当降低 `RERANKER_MAX_LENGTH`。
- 明确设置 `RERANKER_DEVICE=cpu` 验证是否是显存问题。
- 切换到 Qwen3-0.6B 或 BGE。
- 关闭其他占用显存的进程。

### 修改配置没有生效

- 检查 `backend/data/reranker_config.json` 是否覆盖 `.env`。
- 检查模型路径是否以 backend 为基准。
- 重启 FastAPI，确保后台初始化重新创建 ReorderService。
- 查看日志中的模型名、device、max_length 和 dtype。

更多启动问题见 [故障排除](./troubleshooting.md)。
