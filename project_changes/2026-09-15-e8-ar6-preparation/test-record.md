# E8 准备测试记录

最后更新：2026-09-15；状态：`实施中`（准备阶段）。

| ID | 检查 | 结果 | 证据边界 |
|---|---|---|---|
| E8-P01 | E6/E7 closure index verify | 通过 | 证明 E6/E7 证据索引完整，不授权 E8 删除 |
| E8-P02 | 目标容器身份/健康状态观察 | 目标容器已恢复 healthy | 只观察指定目标；不改变 schema 或全局只读 |
| E8-P03 | 最终目标备份文件存在与 SHA 摘要 | 通过 | 备份保留；未覆盖或恢复到当前目标 |
| E8-P04 | Django、Redis、旧目录、MD5、Chroma、Skill objects 盘点 | 已记录 | 目录数量不能代替引用图或删除授权 |
| E8-P05 | new-api ID/启动时间/restart_count/status 观察 | 运行中，未操作；ID 相同、启动时间较 E6/E7 历史快照变化、restart_count 仍为 0 | 当前观察与历史 E6/E7 快照分开，不能宣称本轮未重启 |
| E8-P06 | 删除处置清单审查 | 全部 `delete_enabled=false` | 需要独立备份、对账、回滚和用户批准后才能执行 |

运行命令：

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e8_prepare.py
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/archive_closure.py --verify
```

E8 准备不包含真实删除、服务下线、迁移切换或生产发布测试。隔离副本上的 E6/E7 SQL-only 恢复和真实模型证据作为输入，E8 仍需自己的 FastAPI-only runbook 和三类数据库 smoke。
