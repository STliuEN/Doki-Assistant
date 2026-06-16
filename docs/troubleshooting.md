# 故障排除

## 常见问题

### 1. API Key 错误

**问题**：`Invalid API Key` 或 `API Key expired`

**解决方法**：
- 检查 `.env` 文件中的 `DASHSCOPE_API_KEY` 是否正确
- 确保 API Key 没有过期或权限不足
- 访问阿里云 DashScope 控制台检查 API Key 状态

### 2. 数据库连接失败

**问题**：`Connection refused` 或 `Access denied`

**解决方法**：
- 检查数据库配置是否正确（主机、端口、用户名、密码）
- 确保数据库服务正在运行
- 验证数据库用户权限
- 检查网络连接和防火墙设置

### 3. 向量数据库问题

**问题**：`Permission denied` 或 `Directory not found`

**解决方法**：
- 检查 `data/chromadb` 目录是否存在且有写入权限
- 确保文件权限正确
- 创建缺失的目录：`mkdir -p backend/data/chromadb`

### 4. 前端访问后端 API 失败

**问题**：`CORS error` 或 `Network error`

**解决方法**：
- 检查 CORS 配置是否正确
- 确保后端服务正在运行
- 验证网络连接和防火墙设置
- 检查 API 端点是否正确

### 5. ModelScope / 重排序模型加载失败

**问题**：`RuntimeError: 重排序模型加载失败: [Errno 2] No such file or directory`

或：

```text
OSError: Error no file named model.safetensors, or pytorch_model.bin
```

**解决方法**：

- 检查 `.env` 文件中的 `RERANKER_MODEL_PATH` 是否正确
- 确保模型文件完整下载，目录中应包含 `config.json` 和 `model.safetensors` / `pytorch_model.bin`
- 如果 `models/bge-reranker-v2-m3` 下存在 `._____temp` 或 `.lock`，通常代表 ModelScope 下载中断；重启服务会触发清理和重新下载
- 检查文件权限
- 尝试重新下载模型：删除模型目录后重启服务

### 6. CUDA 内存不足

**问题**：`CUDA out of memory`

**解决方法**：
- 降低 `max_length` 参数（默认为512）
- 减小 `batch_size`（当前设置为1）
- 使用 CPU 模式：在 `reorder_service.py` 中将 `device` 强制设置为 `"cpu"`
- 关闭其他占用 GPU 内存的程序

### 7. RTX 50 系列 / sm_120 无法使用 CUDA

**问题**：日志提示当前显卡是 `sm_120`，但 PyTorch 只支持到 `sm_90`，例如：

```text
NVIDIA GeForce RTX 5070 Ti with CUDA capability sm_120 is not compatible
current PyTorch install supports sm_50 ... sm_90
```

**解决方法**：

- 这是 PyTorch wheel 构建能力问题，不是 RAG 代码问题
- 当前系统会自动回退 CPU，保证 RAG 主链路可继续使用
- 若要使用 5070 Ti 跑 GPU 推理，需要安装支持 `sm_120` 的 CUDA 13.x PyTorch wheel
- 项目后端依赖已切换到 `cu132` index，建议重建 `backend/.venv`
- 可执行：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\rebuild-backend-cu132.ps1
  ```
- MySQL、Chroma 向量库和已上传源文件不需要因为这件事重建

### Qwen3-Reranker-4B 加载很慢或内存不足

**问题**：后端启动后 reranker 预热耗时很长，或出现内存/显存不足。

**解决方法**：

- 确认 `RERANKER_BATCH_SIZE=1`
- CPU 回退模式下 4B 会明显变慢，建议优先完成 CUDA 13.x PyTorch 环境重建
- 如果 GPU 显存紧张，可先保持 `RERANKER_TORCH_DTYPE=auto` 或尝试 `float16`
- 如果仍然无法稳定运行，临时切回 `Qwen/Qwen3-Reranker-0.6B` 或 `BAAI/bge-reranker-v2-m3`
- 切换 reranker 不需要重建向量库

### 8. 依赖安装失败

**问题**：安装 `sentence-transformers` 或 `torch` 失败

**解决方法**：
- 更新 pip：`pip install --upgrade pip`
- 使用镜像源：`pip install sentence-transformers torch -i https://pypi.tuna.tsinghua.edu.cn/simple`
- 检查网络连接
- 手动下载预编译包安装

### 9. 端口被占用

**问题**：`Address already in use`

**解决方法**：
- 查找占用端口的进程：`netstat -ano | findstr :8000`（Windows）或 `lsof -i :8000`（Linux）
- 终止占用端口的进程
- 使用不同的端口启动服务

### 10. 文件上传失败

**问题**：`File too large` 或 `Unsupported file type`

**解决方法**：
- 检查文件大小是否超过限制（单个文件20MB，多个文件总计200MB）
- 确保文件类型为 PDF、TXT 或 DOCX
- 检查文件权限

### 11. 会话历史丢失

**问题**：无法获取会话历史或会话被意外删除

**解决方法**：

- 检查数据库连接是否正常
- 验证用户权限是否正确
- 检查会话 ID 是否正确

## 日志检查

### 应用日志
- 后端日志位于 `backend/logs/` 目录
- 前端日志可在浏览器控制台查看

### 常见错误模式

#### 模型相关错误
```
RuntimeError: 重排序模型加载失败
```
→ 检查模型路径和文件完整性

```
OSError: Error no file named model.safetensors, or pytorch_model.bin
```
→ 模型目录存在但权重缺失或下载未完成

```
CUDA capability sm_120 is not compatible
```
→ 当前 PyTorch wheel 不支持 RTX 50 系列架构，升级到 CUDA 13.x 构建或使用 CPU

#### 数据库错误
```
OperationalError: (2003, "Can't connect to MySQL server")
```
→ 检查数据库连接配置

#### API 错误
```
HTTPException: 401 Unauthorized
```
→ 检查认证令牌是否有效

## 性能问题排查

### 响应缓慢
- 检查数据库查询性能
- 验证向量数据库索引是否正确
- 监控 GPU/CPU 使用率

### 内存占用过高
- 检查模型加载方式
- 优化批次大小
- 考虑使用更小的模型

## 调试技巧

### 启用详细日志
在 `backend/app/core/logger_handler.py` 中设置日志级别为 `DEBUG`

### 测试 API 端点
使用 FastAPI 自动生成的交互式文档：`http://localhost:8000/docs`

### 检查环境变量
```bash
# Windows
echo %DASHSCOPE_API_KEY%

# Linux/Mac
echo $DASHSCOPE_API_KEY
```

## 联系支持

如果问题仍然存在，请提供以下信息：
1. 完整的错误日志
2. 环境配置信息
3. 操作系统和 Python 版本
4. 复现步骤

可以通过项目 GitHub Issues 或联系作者获取帮助。

---

[← 返回首页](../README.md)
