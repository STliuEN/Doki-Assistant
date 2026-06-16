# ModelScope 模型下载配置

## 模型介绍

BAAI/bge-reranker-v2-m3 是北京智源研究院（BAAI）推出的多语言重排序模型，基于 XLMRobertaForSequenceClassification 架构：

- **原生 CrossEncoder 兼容**：BERT 式 Encoder-only 架构，sentence-transformers 原生支持
- **多语言**：支持 100+ 语言，中文和英文表现优秀
- **长上下文**：最大 8192 tokens
- **轻量级**：仅 568M 参数，适合本地笔记本部署

## 安装步骤

### 1. 安装依赖包

```bash
# 进入后端目录
cd backend

# 安装重排序模型依赖
uv add sentence-transformers torch
```

### 2. 模型获取方式

#### 方法一：自动下载（推荐）

系统支持自动检测和下载模型。当 FastAPI 服务器启动时：
1. 自动检查配置的模型路径是否存在
2. 校验目录中是否包含 `config.json` 和完整权重文件
3. 如果目录不存在或权重不完整，自动从 ModelScope 下载模型到指定路径
4. 下载完成后在后台初始化阶段预热加载

**无需手动下载**，系统会在服务器启动时自动完成检查和下载。

注意：目录存在不代表模型可加载。完整目录至少需要包含：

```text
config.json
model.safetensors 或 pytorch_model.bin
tokenizer.json / tokenizer_config.json
```

如果下载中断，ModelScope 可能留下 `._____temp` 或 `.lock` 目录。系统会跳过这些临时目录，检测到模型不完整时会清理临时目录并重新下载。

#### 方法二：手动从 ModelScope 下载

如果需要手动下载：
1. 访问模型页面：[BAAI/bge-reranker-v2-m3 · 模型库](https://www.modelscope.cn/models/BAAI/bge-reranker-v2-m3)
2. 下载完整模型文件到本地目录，推荐路径：
   ```
   ./models/bge-reranker-v2-m3
   ```

## 环境变量配置

在 `.env` 文件中配置模型路径：

```env
# 重排序模型配置（可选）
RERANKER_MODEL_PATH=./models/bge-reranker-v2-m3
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
RERANKER_MODEL_REVISION=master
RERANKER_DEVICE=auto
RERANKER_MIN_WEIGHT_MB=50
```

字段说明：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RERANKER_MODEL_PATH` | `./models/bge-reranker-v2-m3` | 本地模型保存目录 |
| `RERANKER_MODEL_NAME` | `BAAI/bge-reranker-v2-m3` | ModelScope 模型 ID |
| `RERANKER_MODEL_REVISION` | `master` | ModelScope revision |
| `RERANKER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `RERANKER_MIN_WEIGHT_MB` | `50` | 权重文件最小大小校验阈值 |

### 硬件要求
- **CPU 模式**：任意现代 CPU（推荐 8GB+ 内存）
- **GPU 模式**：支持 CUDA 的 NVIDIA GPU（推荐，大幅提升性能）

RTX 50 系列等 `sm_120` 显卡需要使用支持该架构的 PyTorch CUDA 13.x wheel。若当前环境是 `torch + cu126` 且日志提示只支持到 `sm_90`，系统会自动回退 CPU。要启用 GPU 推理，建议重建 `backend/.venv` 并切换到 `cu130` 或 `cu132` 构建的 `torch / torchvision / torchaudio`。

### 软件要求
- Python 3.8+
- PyTorch 2.0+
- sentence_transformers 2.2.0+

## 性能优化建议

1. **GPU 加速**：确保安装了 CUDA 版本的 PyTorch 以获得最佳性能
2. **批量处理**：虽然当前设置 `batch_size=1` 避免 padding 错误，但在文档数量较少时可以尝试增加批次大小
3. **模型缓存**：模型会在服务启动时加载一次，后续请求无需重新加载

## 加载失败诊断

常见错误：

```text
OSError: Error no file named model.safetensors, or pytorch_model.bin
```

含义：模型目录被找到了，但权重文件没有完整下载。

处理建议：

1. 检查 `RERANKER_MODEL_PATH` 是否指向后端项目内的模型目录。
2. 检查实际模型目录是否包含 `model.safetensors` 或 `pytorch_model.bin`。
3. 如存在 `._____temp` 或 `.lock`，通常是下载中断残留；重启服务会触发清理和重新下载。
4. 如果无法联网下载，可手动从 ModelScope 下载完整模型后放入同一路径。

## 版本信息

- 模型版本：BAAI/bge-reranker-v2-m3（XLMRobertaForSequenceClassification）
- sentence-transformers：2.2.0+
- PyTorch：2.0+

---

[← 返回首页](../README.md)
