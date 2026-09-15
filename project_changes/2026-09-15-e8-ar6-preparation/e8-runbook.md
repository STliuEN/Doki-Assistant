# E8 运行与恢复手册

## 必须遵守的边界

所有操作只能指向 allowlist 的 loopback 目标：

- MySQL：`127.0.0.1:33427/doki_e4`
- 不连接主机 3306。
- 不设置 `read_only`/`super_read_only`，不锁全库。
- 不停止、重启或修改 new-api。
- 恢复/验收使用新的隔离目录、容器、网络和 evidence。
- 凭据只通过受保护的本地文件或进程环境传递，不打印。

## 当前服务

FastAPI 18000，前端 18080，Redis 18020，Ollama 11434，MySQL 33427。

## 恢复顺序

1. 备份并记录 SQL SHA、字节数、revision 和目标身份。
2. 在隔离副本恢复 MySQL。
3. 校验表、FK、digest、审计和 pending action。
4. 从 SQL generation 重建 Chroma。
5. 运行 readiness、业务 smoke 和 SQL/Chroma 对账。
6. 通过后恢复 FastAPI 流量。

SQL 是唯一业务恢复来源；Chroma 和 Redis 均可重建。默认 `delete_enabled=false`，历史容器、网络、旧 adapter、MD5 sidecar、旧 Chroma generation 和 fixture 不因 E8 关闭自动删除。
