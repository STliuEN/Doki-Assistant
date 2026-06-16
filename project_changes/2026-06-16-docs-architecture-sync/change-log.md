# 2026-06-16 文档与架构同步

## 更新内容

- 更新 `README.md` 的项目架构图，补充知识库源文件、Embedding 配置、Reranker 配置与 Chroma 索引之间的关系。
- 新增“知识库、Embedding 与 Reranker”说明，记录文档导入、源文件保存、embedding 切换重建索引、reranker 切换不重建索引的完整链路。
- 更新项目结构，补充 `knowledge_document.py`、`embedding_config.py`、`embedding_config_service.py`、`reranker_config_service.py` 和 `knowledge_document_service.py`。
- 新增 Embedding 与知识库索引配置说明，明确 Ollama embedding 模型读取和切换行为。
- 更新 `docs/project_develop.md`，记录知识库模型配置、源文件可追溯索引和当前 RAG 数据链路。

## 当前链路

```text
上传文件
  -> 保存源文件和文档元数据
  -> 解析并切片
  -> 使用当前用户 embedding 写入 Chroma
  -> 查询时召回知识库 / 笔记候选
  -> 使用当前 reranker 重排序
  -> 拼接上下文并调用 LLM
```

## 说明

- Embedding 是用户级配置，切换后会重建知识库和笔记索引。
- Reranker 当前是本地全局配置，切换后只影响后续检索排序。
- Skill/Tool 仍保持独立文件模块结构，默认全开以复刻初版 Agent 链路。
