# E6/E7 期间开发账号登录修复

2026-09-14，用户要求优先排查 STliuEN；密码验证失败时允许直接修复本地数据库管理员账号，完成后继续 E6/E7。

2026-09-15 更新：用户随后指定使用本人名字新建管理员，已创建并验证 `STliuEN-security-admin`（security_admin）。E6/E7 联合已关闭，当前 SQL runner 已显式启用；下方账号恢复过程为历史记录，最终状态见[收口判定](./closure-review.md)。

## 诊断与处理

- 实际权威库：`127.0.0.1:33427/doki_e4`，原 Doki 容器 ID/UUID 均已核对；没有访问主机 3306。
- STliuEN 存在且 active，canonical ID `2e2c05f2-d031-527e-b463-93c9f0cccbfa`。原 Argon2id hash 有效，但用户本次提供的密码未通过（同时检查普通下划线和字面反斜杠两种结尾）；不据此断言用户记错或追认未知历史改密来源。
- Doki 前后端原先均未运行，也是页面不可用的独立原因。
- 另发现 Django PBKDF2 兼容实现把 `sha256`/`sha1` 截成 `256`/`1`；已修正并用已知测试向量验证。该错误与本账号的 Argon2id 不匹配无直接因果关系。
- 先二进制备份并恢复到新副本 `doki-e6e7-accept-55df5004`，41 表数据摘要一致。副本修复成功后，确认目标仍与该备份完全相同，再按同一操作修复目标。
- 在单一事务中重置 STliuEN 为用户提供的普通下划线结尾密码、增加 `skill_admin`、提升 token version、撤销原 3 个 active session，写入 `auth.local_account_recovered` 审计。没有新建替代用户或变更原笔记/知识/聊天归属，没有授予 `security_admin` 或批准 Skill grant。
- 密码、数据库凭据、hash、cookie、JWT 不写入公开报告。备份和私有执行材料保留在 `.runtime/e6e7-login-*`。

## 验证

- 已知 PBKDF2 向量、Argon2id、token 生命周期：16 passed；E4/E5/E6E7 guard：29 passed；本次文件 Ruff/diff 通过。
- 真实目标 HTTP 经 Vite 代理：错误密码 401、正确密码登录 200、资料 200、refresh 200、Skill catalog 200、logout 200、注销后原 token 401。
- Playwright 使用真实 Edge：登录后到 `/notes`，7 条原笔记可见；进入 `/skills`，10 条原 Skill 及“导入本地 ZIP / 新增 Skill / 管理设置”等管理员入口可见。浏览器控制台 0 errors、2 条框架提示 warnings。
- 完整 `main:app` 已启动，开发地址 `http://127.0.0.1:18080`，后端仅 `127.0.0.1:18000`。保留正常限流；新建独立 Redis `doki-e6e7-dev-redis-20260914`（128 MiB、0.5 CPU、loopback 18020），没有调整其他 Redis 或主机服务。
- 暂未启用 SQL runner，避免账号修复过程消费历史/新增业务 job；后续 E6/E7 联合验收与迁移继续独立执行。
- `new-api` ID、启动时间、restart count 均未变化；MySQL 全局只读设置未修改。

## 后续阶段边界

账号恢复时尚待指定安全管理员的缺口现已解决。`STliuEN` 保持 skill_admin，`STliuEN-security-admin` 为不同 ID 的 security_admin；8 个本地 Skill 经申请、审批并启用，目标图文事务夹具与 SQL-only 恢复通过，JV01–JV09 已关闭。两个账号由同一用户授权操作，不宣称两名自然人独立复核。E8、旧输入物理删除与全局门禁继续冻结。

证据：[脱敏报告](./artifacts/login-recovery.json)、[浏览器截图](../../output/playwright/e6e7-login-skill-admin.png)。
