# E4-PREP-07 路由匹配证据

日期：2026-09-02  
范围：只读静态/隔离导入；未连接数据库、Redis、Chroma 或在线 API。

## 命令

在 `backend` 目录使用已存在的 `.venv`，仅设置通过 E3 guard 格式校验的合成 URL 以便导入 router；该命令不执行网络或数据库操作：

```powershell
$env:E3_DATABASE_URL='mysql+aiomysql://app:pass@127.0.0.1:33327/doki_e3?charset=utf8mb4'
& '.\.venv\Scripts\python.exe' -c "from app.router.note_template_router import note_template_router; scope={'type':'http','path':'/note-template/reorder','method':'PUT','root_path':'','scheme':'http','query_string':b'','headers':[],'client':('x',1),'server':('x',1)}; print([(r.name, str(r.matches(scope)[0]), r.matches(scope)[1]) for r in note_template_router.routes])"
```

## 结果摘要

- `PUT /note-template/{template_id}` 注册于具体 reorder 路由之前。
- 对 `/note-template/reorder` 的首个 `Match.FULL` 是 `update_template`，`path_params` 为 `template_id=reorder`。
- 后续 `reorder_templates` 路由也能完整匹配，但按顺序不会被首个匹配路由选中。

## 原始处置（已完成）

该问题曾登记为 E4 实施前阻断。已将具体静态路由置于通用参数路由之前，并加入 `backend/tests/test_note_template_route_matching.py`；纯路由回归通过。该证据不代表业务 API、停写、迁移或切换已通过。

## 回归结果（2026-09-02）

`tests/test_note_template_route_matching.py`: `1 passed`。首个 `Match.FULL` 为 `reorder_templates`，`path_params` 为空；未建立数据库或外部服务连接。
