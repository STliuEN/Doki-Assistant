# E8 验收记录

最终状态：**passed / closed**

- 后端：539 passed，1 warning；Ruff、compileall passed。
- smoke：current、restored、empty-schema passed。
- RAG：Vector、BM25、HyDE、Reranker、Combined、empty-owner passed。
- SQL：43 tables、58 FKs、package/source digest passed、checked orphans 0。
- SQL→Chroma：6 owners、12 artifacts passed。
- readiness：HTTP 200。
- RPO：0 committed writes lost；RTO：3.752 seconds。
- new-api：running，restart_count=0，未修改。
- MySQL global read_only/super_read_only：0/0，未修改。
- reference audit：passed。

证据文件：

- `artifacts/e8-final-decision-20260915.json`
- `artifacts/e8-final-gates-20260915.json`
- `artifacts/e8-sql-reconciliation-20260915.json`
- `artifacts/e8-rpo-rto-20260915.json`
- `artifacts/e8-reference-audit-20260915.json`

runtime 大文件和私有凭据只保存在本机 .runtime。
