# E5 RAG 投影

E5 的结果已纳入 E8 收口：

- SQL 保存 generation、artifact、owner state 和任务状态。
- Chroma 仅保存 SQL generation 构建的 owner-scoped 投影。
- Vector、BM25、HyDE、Reranker、Combined、empty-owner 分支均有真实证据。
- 投影缺失、owner 不匹配或 generation 不一致时，业务路径 fail-closed 或返回受控错误。
- 旧 MD5、Vector 和文件路径只保留作维护/兼容。

E8 对 6 个 owner、12 个 artifact 完成 SQL→Chroma 对账，并通过三类业务 smoke。重演必须使用新 fixture 和 evidence；不得连接主机 3306、设置全局只读或修改 new-api。
