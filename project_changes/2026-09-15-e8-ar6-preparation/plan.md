# E8/AR-6 执行计划与最终状态

## 目标

验证 SQL authority、SQL pending action、可重建 Chroma、恢复能力和主机服务边界，完成本地单机重构收口。

## 最终判定

**closed**，关闭时间 2026-09-15，remaining_blockers 为空。关闭范围为 E8 SQL authority 与本地最终门禁。

## 验收结果

- 后端回归：539 passed，1 warning；Ruff、compileall 通过。
- current、restored、empty-schema 业务 smoke 通过。
- Vector、BM25、HyDE、Reranker、Combined、empty-owner 通过。
- SQL：43 tables、58 FKs、digest 通过、检查范围内孤儿为 0。
- SQL→Chroma：6 owners、12 artifacts 通过。
- RPO：0 committed writes lost；RTO：3.752 seconds。
- /health/ready：HTTP 200。
- new-api：running、restart_count=0、未修改。
- MySQL global read_only/super_read_only：0/0、未修改。

这些属于个人部署或生产化场景的独立范围，不属于 E-number 的剩余工作。
