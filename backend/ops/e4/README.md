# E4 业务迁移

E4 是 SQL 业务迁移和本地单实例切换阶段，结果已由 E5、E6/E7 和 E8 最终证据承接。

历史目标包括专用 target、owner/FK/digest/审计校验、恢复副本和旧服务边界。E4 容器、备份和日志保留在历史 runtime 与 project_changes 中。

重新演练必须使用新的隔离目录、allowlist、备份和 preflight，不得复用旧 stop 文件，也不得连接主机 3306。当前业务权威和关闭状态以 E8 final decision 为准。
