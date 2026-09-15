# 架构重写计划与收口状态

## 目标

把业务事实收敛到 MySQL，把 RAG 收敛为 SQL generation 驱动的可重建投影，并用 owner、审计、任务和恢复证据形成闭环。

## 已完成

E8 最终证据确认：

- 43 张表、58 个 FK、package/source digest 对账通过。
- 检查范围内孤儿记录为 0。
- current、restored、empty-schema 业务 smoke 通过。
- Vector、BM25、HyDE、Reranker、Combined、empty-owner 六条 RAG 分支通过。
- 6 个 owner、12 个 artifact 的 SQL→Chroma 对账通过。
- RPO/RTO、readiness、new-api 不变性和引用审计通过。
- remaining_blockers 为空，状态为 closed。

## 处置原则

旧模块保留为兼容或维护路径，并在 E8 业务边界 fail-closed；本次关闭不要求其物理删除。如需个人部署或生产化，再另建发布项目定义部署、HA、外部依赖、灰度回滚和资源清理门禁；这些不属于 E-number 的剩余工作。
