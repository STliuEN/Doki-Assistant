# E5 执行、恢复与验收工具

本目录提供当前 E5 的受控执行和复验入口。最终状态见 [E5 收口判定](../../../project_changes/2026-09-10-e5-ar4-rag-projection/closure-review.md)，原始成功结果保留在批次 artifacts，凭据/备份仅在 `.runtime`。

## 环境与不可越界事项

- 从仓库根目录使用 `backend/.venv/Scripts/python.exe -X utf8`；本机 Python 3.12、Docker、Ollama、Chroma 与完整本地 Qwen3 reranker 缓存须可用。依赖缺失则退出，不默认下载模型或重启既有服务。
- 原目标固定检查容器 `doki-e4-20260903-mysql` 的精确 ID、端口 `127.0.0.1:33427`、database `doki_e4`、server UUID 与 image。身份不符不得修改常量绕过验证。
- 读取 `.runtime/e4/live-credentials.json` 的 target 专用凭据，只传到进程环境；不打印。禁止 host 3306、MySQL 全局只读/全库锁、停主机既有服务、改变 new-api 的连接或权限。
- 每个新验收目录生成独立 MySQL 容器/卷/网络、loopback 随机端口和私有 Chroma；容器限制 2 GB/2 CPU。故障注入只用于新副本。本轮副本已停止；新复验应使用新目录，不覆盖旧结果。
- `stage: E5` allowlist 必须恰有一个 container-backed target。共享 E4 preflight 工具处理该明确 E5 模式，每次调用新生成、有效期 900 秒；普通 E4 完整清单合同仍保留。SQL 进程锁先于消费，runner 并发 1。
- 模型缓存路径来自 E5 本地白名单，SQL query config 保存模型 digest，旧 reranker sidecar 不再是查询权威。真实模型会占用本机 GPU/CPU；容器元数据稳定不等于整机负载不变。

## 只读原目标复核

下面两个入口只在自己的 SQLAlchemy 连接上允许 SELECT/SHOW，不修改服务器全局只读设置，也不启动 consumer。输出必须新命名。

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/verify_closure.py --inventory-only --output .runtime/e5-next-inventory.json
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/verify_closure.py --output .runtime/e5-next-smoke.json
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/final_audit.py --output .runtime/e5-next-audit.json
```

smoke 使用源码中的 UTF-8 固定查询，验证真实 vector/BM25/HyDE/rerank/combined/empty、有限分数、top-k、source/generation 和前后 SQL/new-api 清单；不单独证明质量/HTTP/UI。`final_audit.py` 复算 SQL chunks，校验全部 active collection、FK、staging/cleanup 和未登记 collection。

## 从新恢复副本执行验收

下面命令会创建资源、写副本和调用模型，已在本轮 E5 授权范围内实施。每轮换一个目录，例如 `.runtime/e5-replay-next`，按依赖顺序执行。不要用 PowerShell 文本管道传递 SQL dump；工具通过二进制 stdin/stdout 备份/恢复。

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/acceptance_env.py .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/schema_acceptance.py --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/acceptance_runtime.py rebuild --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/quality_acceptance.py --directory .runtime/e5-replay-next --freeze
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/quality_acceptance.py --directory .runtime/e5-replay-next
```

`acceptance_env` 先备份当前 target，恢复到新副本并逐表 counts/digest 对账，再发出新副本 allowlist。`schema_acceptance` 在副本内新建空库/populated 测试库；populated 输入固定为已有、摘要校验的 pre-E5 dump `.runtime/e4/backup-target-bbcf14de7d4024aa.sql`，缺少则停止。`rebuild` 使用真实 guarded runner 从 SQL 向全新 Chroma 重建，不导入旧向量。

质量冻结必须先于当前运行；8 条来源、阈值和输入 SHA 由 quality-plan 固定，不能为通过而更改。同一语料用户已确认来源；新语料需重新来源核定。当前结果中的用户核定发生在测试之后，不能宣称测试前独立盲标。每分支首请求＋7 暖样本的 p95 是样本统计。

## HTTP、故障和浏览器

在独立终端启动验收 API：

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/acceptance_runtime.py serve --directory .runtime/e5-replay-next --port 18050
```

该 API 包含生产 routers/middleware/异常处理器及真实 SQL/Chroma；省略无关 main 启动任务，仅在 harness 关闭限流以隔离 Redis 不可用。不能据此宣称完整部署/main/Redis/MCP 已验证。随后依序运行：

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/http_acceptance.py --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/lifecycle_acceptance.py pause --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/lifecycle_acceptance.py recover --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/lifecycle_acceptance.py cancel --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/fault_acceptance.py --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/storage_fault_probe.py corrupt --directory .runtime/e5-replay-next
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/storage_fault_probe.py permission --directory .runtime/e5-replay-next
```

lifecycle 的 pause 会启用真实 consumer，并在 Chroma build 后人为暂停；recover 只核对并终止它创建的 PID，再等待 lease/fence 回收。重复运行必须使用新目录，旧 stop-file 不得误作新退出信号。storage fault 仅破坏新建目录中的 SQLite 或临时 Windows ACL，finally 移除其拒读 ACL，保留故障文件。

浏览器需要本轮单独 Vite（`VITE_BACKEND_TARGET=http://127.0.0.1:18050`、端口 18081）及 Playwright CLI/Edge 专属会话 `e5-acceptance`。仅将副本产生的 `browser.private.json` 加载到该会话，禁止导出登录状态到 artifacts。`browser_capture.py NAME --directory DIR [--reload] [--edit]` 保存已建立会话中的实际页面结果和截图，NAME 包括 queued/building/failed/ready/query-saved/index-queued/restarted/api-restarted/chunks/upload/uploaded。状态转换需配合 consumer 和 lifecycle；截图脚本不伪造 SQL 状态。

## 原目标最终重建和收尾

```powershell
# 无 --execute 只准备本轮备份/guard；执行时同样先核对身份并生成即时 preflight。
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e5/finalize_target.py --directory .runtime/e5-final-next --execute
```

仅在新副本验收通过后用于原授权 E5 target。脚本先二进制备份、绑定代码/备份摘要及即时 preflight，再获 SQL 进程锁，原子保存查询指纹和两用户重建请求，消费至 ready 后正常停止。它不处理历史 enrichment 死信，不启动 E6。

停止验收 consumer 使用本轮指定 stop-file 并等待 drain；只停止核对过命令/PID 的验收 API/Vite 和精确 allowlist 对应的新副本，关闭专属浏览器会话。保留容器/卷/网络、坏/好 dump、旧 Chroma/sidecar 和 E1–E4 材料；禁止 close-all、全局 kill 或删除资源。原目标和主机既有服务继续运行。

`archive_closure.py` 只从当前已完成的固定 E5 私有目录提取白名单结果、生成机器门槛和 SHA 索引，不能替代真实测试。`--seal` 需要当前 checks.json 已确认全部门禁；不连接数据库或模型。历史 `restore_rehearsal.py` 只证明旧 post-schema 恢复，不能替代本轮完整链路。
