# 架构执行交接

## 交接结论

E8/AR-6 已关闭。当前业务基线是 MySQL SQL authority、SQL pending action 和 SQL generation 驱动的 Chroma 投影。

证据入口：

- [最终判定](../project_changes/2026-09-15-e8-ar6-preparation/artifacts/e8-final-decision-20260915.json)
- [最终门禁](../project_changes/2026-09-15-e8-ar6-preparation/artifacts/e8-final-gates-20260915.json)
- [SQL 对账](../project_changes/2026-09-15-e8-ar6-preparation/artifacts/e8-sql-reconciliation-20260915.json)
- [RPO/RTO](../project_changes/2026-09-15-e8-ar6-preparation/artifacts/e8-rpo-rto-20260915.json)
- [引用审计](../project_changes/2026-09-15-e8-ar6-preparation/artifacts/e8-reference-audit-20260915.json)

## 接手检查

```powershell
git status --short
backend\.venv\Scripts\ruff.exe check backend\app backend\ops backend\tests
backend\.venv\Scripts\python.exe -m compileall -q backend
```

确认目标是 allowlist 中的 `127.0.0.1:33427/doki_e4`，不连接主机 3306，不设置全局 read_only/super_read_only，不停止或修改 new-api。恢复、迁移和删除均须使用新隔离目录、备份、allowlist 和回滚记录。

## 故障处置

业务事实从 SQL 恢复，Chroma 从 SQL generation 重建，Redis 只重新建立缓存/限流状态。旧兼容路径命中 E8 业务边界时必须 fail-closed。

## 未包含在 E8

生产拓扑、DNS/LB/TLS、HA、共享存储、外部 MCP/模型完整矩阵和历史代码/资源的物理清理属于独立生产化工作，不是 E-number 未完成项。
