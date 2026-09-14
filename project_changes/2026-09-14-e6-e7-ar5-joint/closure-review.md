# E6/E7 联合关闭判定

日期：2026-09-15（Asia/Taipei）。判定：**E6、E7 联合已关闭**，限本机 SQL 权威与 A/有限 B Skill 范围；无剩余范围内阻塞。用户已持续授权完成剩余缺口，并指定使用本人名字新建安全管理员。

## 目标结果

- 目标仍为 `doki-e4-20260903-mysql`、`127.0.0.1:33427/doki_e4`，schema `20260914_0010_e6e7_sql_authority`。
- `STliuEN` 为 skill_admin；新增 `STliuEN-security-admin` 为 security_admin，两个账号 ID 不同。新账号密码校验、API 登录、浏览器登录与授权面板已验证。凭据仅保存在 `.runtime/e6e7-target-closure-20260914/security-admin.private.json`。
- 10 个 Skill/version/alias 保持稳定身份，10 个规范包与 10 个 legacy_canonical 上传字节已在 SQL。目标 `skill_imports=0`：历史迁移不伪造用户导入请求。
- 8 个本地 Skill 经申请、不同账号审批和生命周期启用；`mcp-smoke-test`、`public-info-lookup` 涉及外部 MCP，保留声明并保持 disabled/unsupported。授权约 30 天到期，延期需重新审批。
- 6 份原文、7 篇笔记保持原数量。历史图片为 0；目标带图 Markdown 事务夹具完成提取、读取、跨用户拒绝、损坏拒绝及 source/link/asset 三层回滚核验。
- Doki 开发入口 `http://127.0.0.1:18080`，健康状态 `ok`；SQL runner 并发 1、running/idle。健康接口已退出旧 Skill 文件探测，RAG 明确按用户独立 generation 判断。

## 验收证据

完整 JV01–JV09 对照见 [contracts.md](./contracts.md)。结构化结果见 [closure-decision-20260915.json](./artifacts/closure-decision-20260915.json)，代码与证据摘要见 [closure-index-20260915.json](./artifacts/closure-index-20260915.json)。

| 项目 | 结果与证据 |
|---|---|
| schema / 备份 | 新空库迁移至 0010，42 表恢复；备份前后 data-only SHA 相同。最终目标另做完整备份及新副本恢复 |
| 包生命周期 | 真实 MySQL 并发幂等、相同幂等键不同字节冲突、危险 ZIP 隔离、publish 后 disabled、原始/规范/资源摘要及导出重导入 |
| 角色与运行授权 | 临时同时拥有两角色的请求人自批仍 403；普通用户拒绝；独立账号批准。enabled 正向控制后注入过期/摘要漂移，均 403，回滚后恢复正例 |
| 撤销传播 | 真实 RunBinding、资源读取、工具写笔记和带 Skill 来源的 SQL job 正例；撤销后新 Run、既有工具、资源、任务入口、延迟确认均拒绝，无第二条笔记副作用 |
| 图文 | 生产 ingest 提取带图 Markdown；SQL download/batch、跨用户、同名/同 MD5 不同 owner、源删除级联、源或图像字节损坏准确拒绝 |
| HTTP/SSE | 真实路由及 SQL，两个隔离测试用户登录；上传 SSE accepted、图片/batch、笔记创建/列表；本机 Ollama qwen3:0.6b 实际调用时间工具，回答及会话/消息/RunBinding 落库；跨会话 owner 403 |
| 故障 | 隔离副本 SQL 停止时受保护图片请求 500 且无数据/文件 fallback，非数据库路由仍响应；固定端口重启后认证图片恢复。SQL 包损坏及空 Chroma 明确拒绝；恢复后的 revoked Run 不复活 |
| SQL-only 恢复 | 带包/资源/媒体/配置/grant/audit 的 SQL 备份恢复到另一新卷，无旧 objects/media；真实 embedding 重建全新 Chroma，逐条核对 ID、正文、元数据、向量维数。夹具副本 chunks 为 58/13、0/0、1/0；与其 SQL 输入一致，不混作目标 57/11 基线 |
| 回归 | 最终后端 **539 passed**（1 条 aiosqlite datetime 弃用警告），前端 **29 passed**，lint/build、Ruff、compileall、diff 检查通过；管理员真实浏览器截图已留存 |

## 修复与更正

首次聊天曾在父会话建立前写 RunBinding，触发 `Canonical parent session is missing`。现将父会话与绑定置于同一事务，补充真实 HTTP 和持久化回归；外部用户不能借用已有 session。健康检查也已改为 SQL 包核验，避免旧文件目录成为运行依赖。

旧 `e6-e7-final-decision.json` 为历史未关闭记录，不再代表当前状态：其中 `skill_imports=10` 为误记；“历史图片 0 必须补用户真实数据”不符合 JV05。旧授权脚本的自批用例只证明角色拒绝，漂移用例未先证明 enabled；旧媒体脚本捕获了泛化异常。新证据使用准确状态码、正向控制、SQL-only 恢复和明确夹具边界取代这些不足。

目标授权脚本曾在部分提交后因 ORM 回滚失效及懒加载中断。现使用标量 ID 续跑并通过 lifecycle API 补齐启用 revision/registry/audit。7 个早期部分批准保持历史事实，最终完整核验 8 个有效 grant。失败输出和中间材料保留，不抹去执行过程。

## 范围与保留项

本次验证两个不同应用账号，由同一用户授权自动操作；不宣称两名自然人独立复核。目录解析、复杂版本冲突、lease/cancel 等细分边界由全量自动回归覆盖；真实模型、MySQL、HTTP/SSE、恢复和重启结果另列，不把测试替身说成真实基础设施。

没有连接主机 3306，没有修改 MySQL 全局只读或 new-api 的配置/权限/进程。new-api 的容器 ID、StartedAt、restart_count=0 和 running 状态前后一致。旧包、sidecar、备份、失败输入、副本容器/卷/网络全部保留。

E5 仍已关闭；本判定不启动 E8，不开放 C/scripts、网络/secret/外部进程或 package MCP，不解冻 SKILL-GATE、ARCH-GATE 或产品工作包 7–10。旧输入物理删除仍属于后续独立范围。
