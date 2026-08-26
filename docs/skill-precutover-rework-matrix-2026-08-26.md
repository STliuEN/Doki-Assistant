# Skill 提前切片返工矩阵（2026-08-26）

状态：影响评估；不是代码已修复或门禁通过证明。

AR-0 的 P0 止血会触及 08-24 已提前落地的 parser、Skill domain、revision/outbox、Registry、Storage 和 API/UI 切片。以下矩阵用于每项改动后重新核对，不允许以既有 216 passed 或静态产物跳过真实依赖/恢复验证。

| 提前切片 | 关联代码/文档 | P0 止血影响 | 必须复核/返工 | 退出证据 |
|---|---|---|---|---|
| parser / package validator | `backend/app/skills/package.py`, `schema.py`; Skill 规格 §3、§8 | `installed_disabled`、digest 重验和 quarantine 可能改变导入终态与错误映射 | 保留标准 frontmatter/恶意包拒绝；补 archive digest、大小/元数据重验、坏包不产生活跃版本；核对 `409/413` 与 ZIP 错误 envelope | fixture 清单、命令、预期/实际错误码；第三方包仍“未验证”直到真实 API E2E |
| Skill domain / lifecycle | `backend/app/models/skill_domain.py`, `backend/app/skills/service.py`; 08-24 plan §4 | 服务端固定 `installed_disabled`、授权分权和 active pointer 原子性会触及 Import/Installation/Version 状态 | 设计状态迁移兼容；approve/publish/activate/rollback 以 Storage digest preflight 为前置；失败保留上一健康版本并记录审计 | 事务回滚、digest mismatch、重复/中断和权限负向测试；真实 MySQL 未就绪则标“未验证” |
| revision / outbox | `backend/app/skills/service.py`（`_bump_registry`/reconcile）; Skill 规格 §4.2、§7.3 | 坏包或 reconcile 失败不得 ack、不得用同 revision degraded 空快照覆盖健康快照 | 明确逐 consumer ack、幂等键、失败重试和单实例 fencing；AR-0 先保持 fail-closed，AR-1 再交付 durable worker | 单实例 worker kill/restart、重复/乱序和 stale `503` 证据；多实例收敛移 PUBLIC-HA-GATE |
| Registry snapshot / reconcile | `backend/app/skills/registry.py`, `backend/app/agent/skill_registry.py` | 单包损坏隔离与上一健康快照保留改变加载/发布边界 | 按 Skill 隔离加载，失败进入 quarantine/degraded；禁止全局空快照成功；Run 绑定 revision/digest | 临时损坏、缺 collection、重启恢复；快照前后 digest 对账 |
| canonical Storage | `backend/app/skills/storage.py`; Skill 规格 §7、§14.5 | 激活前重验、staging TTL、orphan/GC 会影响 finalize 和回滚路径 | 增加引用状态、quarantine、引用感知 GC；DB commit/finalize 部分失败可对账；不可变对象不覆盖 | 隔离 Storage fixture 的 checksum、GC dry-run/执行、恢复演练；不连接现有 Storage |
| API / router / OpenAPI | `backend/app/router/skill_router.py`, `backend/openapi.json`; 安全计划 API-01 | 禁止一步启用和稳定错误合同会改变响应状态、media type、CORS 和轮询终态 | 修订 `409/413`、ZIP export media type、结构化错误、`Idempotency-Key` CORS，移除虚假 `200 Any`；同步前端类型 | OpenAPI 生成/漂移、API 负向和浏览器预检；无 Node/npm 时前端“未验证” |
| MCP / Tool policy binding | `backend/app/agent/mcp/config.py`, `mcp_router.py`; 架构计划 §2.2 | YAML 写入冻结会使管理 API 进入 adapter/cache 或 fail-closed | 不把本地 YAML 当最终权威；为 AR-3/AR-5 预留 MySQL revision/digest、RunBinding 和回滚合同 | YAML 写入边界静态检查；版本化权威和多实例证据未完成前保持阻断 |
| 前端 Skill 管理 | `front/src/pages/SkillManager.tsx`; Skill 规格 §5、§7 | 服务端状态约束会使前端“批准并安装”流程不能直接启用 | UI 只显示 `installed_disabled`，不能将 `enabled=false/default=false` 当服务端不变量；同步错误/轮询合同 | 依赖恢复后重新运行 Vitest/lint/build/E2E；历史 08-24 结果不作为当前证据 |
| seed / Legacy migration | `backend/app/skills/seed.py`, `seed_packages/`; 新增 Legacy inventory | seed 与历史 YAML 的 alias、Tool、排序、默认状态可能不一致 | 使用 [Legacy inventory](./legacy-skill-inventory-2026-08-26.md) 作为只读输入；实现通用 migrator、checksum、影子对账；缺失字段单独批准 | inventory digest、逐项映射、幂等重跑、零数据/不可恢复报告和观察期 |
| characterization / tests | `backend/tests/test_skill_*`; 08-24 test-record | P0 修复可能使已有测试只覆盖旧局部语义 | 将“已覆盖子集”和“发布门禁”分开；新增真实依赖、故障注入、恢复、授权负向测试 | 每条证据含环境/命令/fixture/阈值/日志/负责人；未执行项保持未验证 |

## 使用规则

1. 每次 P0 改动先在本矩阵标记受影响切片和返工范围，再提交代码与测试。
2. 发现 parser/domain/outbox 的状态或合同变化时，必须同步更新 OpenAPI、Skill 规格和对应 `project_changes` 三件套。
3. 矩阵完成不等于 AR-0 退出；真实依赖、备份恢复、前端复跑和跨平台证据缺失时，状态仍保持 `AR-0 + SK-0`。
