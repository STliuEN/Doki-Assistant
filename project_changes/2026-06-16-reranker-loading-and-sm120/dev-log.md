# 2026-06-16 重排序模型加载与 5070 Ti / sm_120 评估

## 背景

RAG 测试时发现重排序模型没有正确加载。排查后确认问题不在 RAG 检索本身，而是在 reranker 初始化阶段：

- `RERANKER_MODEL_PATH=./models/bge-reranker-v2-m3` 对应的目录存在。
- 实际可加载目录 `backend/models/bge-reranker-v2-m3/BAAI/bge-reranker-v2-m3` 缺少 `model.safetensors` 或 `pytorch_model.bin`。
- `._____temp` 目录中存在未完成下载残留，说明 ModelScope 下载过程中断过。
- 当前环境为 `torch 2.12.0+cu126`，可以检测到 RTX 5070 Ti，但该 wheel 只支持到 `sm_90`，不支持显卡的 `sm_120`。

## 本次代码侧修复

本次只修复 reranker 加载链路，不改变知识库、embedding、Skill/Tool 架构。

### 后端重排序服务

文件：`backend/app/rag/reorder_service.py`

- 将“目录存在即视为模型可用”改为完整模型校验。
- 校验内容包括：
  - `config.json`
  - `model.safetensors` / `model-*.safetensors`
  - `pytorch_model.bin` / `pytorch_model-*.bin`
  - 权重文件大小下限，默认 `RERANKER_MIN_WEIGHT_MB=50`
- 支持在 ModelScope 下载后的嵌套目录中寻找真实模型目录。
- 跳过 `._____temp` 和 `.lock` 这类下载临时目录。
- 检测到不完整模型时清理 ModelScope 临时目录并重新下载。
- 新增 `RERANKER_MODEL_NAME` 和 `RERANKER_MODEL_REVISION` 环境变量扩展点。
- 新增 `RERANKER_DEVICE`，默认 `auto`。
- 在自动设备选择中，如果 PyTorch CUDA 构建不支持当前 GPU 架构，则回退到 CPU。

### 后台初始化

文件：`backend/app/core/background_init.py`

- 原来只做路径检查和 `ReorderService()` 实例化，第一次 RAG 调用时才真正加载 CrossEncoder。
- 现在启动后台初始化阶段会调用 `warmup()` 真实预热 reranker。
- 如果预热失败，记录错误并继续启动服务，避免 reranker 问题阻断整个后端。

### RAG 降级

文件：`backend/app/rag/rag_service.py`

- 如果 reranker 服务尚未初始化，RAG 会跳过重排序并返回原始检索结果。
- 目标是保证知识库问答链路可用，reranker 作为增强层失败时不拖垮主链路。

## 当前执行链路

```text
FastAPI 启动
  -> background_init.start()
  -> ReorderService()
  -> warmup()
  -> check_and_download_reranker_model()
  -> 校验本地模型目录
  -> 不完整则清理 ._____temp/.lock 并从 ModelScope 重新下载
  -> CrossEncoder 加载模型
  -> 设备选择 auto：CUDA 可用且支持当前 GPU 架构则用 cuda，否则 CPU
```

RAG 请求链路：

```text
知识库/笔记检索
  -> 合并候选文档
  -> init_manager.reorder_service.reorder_documents()
  -> CrossEncoder.predict(query, document)
  -> 按分数降序排序
  -> 取前若干文档交给 LLM 总结
```

如果 reranker 未就绪或加载失败：

```text
知识库/笔记检索
  -> 合并候选文档
  -> 跳过重排序
  -> 使用原始检索顺序进入总结阶段
```

## 5070 Ti / sm_120 依赖评估

当前本机日志显示：

```text
torch 2.12.0+cu126
GPU: NVIDIA GeForce RTX 5070 Ti
CUDA capability: sm_120
current PyTorch install supports sm_50 ... sm_90
```

这意味着当前 PyTorch wheel 能看到显卡，但不能用这张显卡做 CUDA 推理。

结论：

- 只升级 NVIDIA 驱动通常不够。
- 只安装本机 CUDA Toolkit 通常也不够。
- 需要把后端 `.venv` 中的 PyTorch 换成支持 `sm_120` 的 CUDA 13.x 构建。
- 更稳妥的做法是重建后端虚拟环境，而不是在旧 `.venv` 上叠加安装。

建议后续迁移目标：

```text
torch -> cu132 构建
```

需要重建的范围：

- `backend/.venv`
- `backend/uv.lock` 中 PyTorch index 与锁定版本

不需要因为这件事重建的范围：

- MySQL 数据库
- Chroma 向量库
- 已上传源文件
- 当前 embedding 模型配置

## Ollama reranker 评估

Ollama 可以作为未来可选 reranker provider，但不建议直接替换当前 CrossEncoder 默认链路。

原因：

- Ollama 官方接口主要是 chat/generate/embed，没有标准 rerank endpoint。
- 使用 Qwen3-Reranker 等模型时，需要通过 generate/logprobs 自己封装 `query-document` 打分逻辑。
- 批处理和吞吐通常不如本地 CrossEncoder 直接 `predict(pairs)`。
- 适合作为可切换实验后端，而不是当前默认稳定后端。

建议未来架构：

```text
RerankerProvider
  -> sentence_transformers_cross_encoder  # 默认
  -> ollama_generate_logprobs             # 可选实验
  -> vllm_reranker                        # 未来高性能部署
```

## 验证

- `uv run python -m compileall app` 通过。
- 本地诊断确认当前 reranker 模型目录不完整。
- 本地诊断确认当前设备自动选择为 `cpu`，避免不兼容的 CUDA 路径。
