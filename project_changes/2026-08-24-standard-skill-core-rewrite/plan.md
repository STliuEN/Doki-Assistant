# 标准 Skill 核心重构计划

日期：2026-08-24

状态：A 级和有限 B 级开发支持已形成；C 级未实现；`SKILL-GATE` 未通过

关联记录：同目录 `change-log.md`、`test-record.md`

## 背景与决策

Doki 原有 Skill 使用私有 `skill.yaml + SKILL.md`、源码目录写入和进程内 Registry，不能直接承载只有标准 `SKILL.md` 的第三方 package，也缺少不可变版本、授权、回滚和隔离执行合同。

本重构固定采用以下方向：

- 所有来源统一为根目录包含标准 `SKILL.md` 的版本化 package。
- MySQL 保存 Skill/版本/安装/授权/运行绑定事实，仓库外 Storage 保存 canonical immutable archive。
- 前端提供新建、导入、审批、编辑、资源管理、配置、版本、回滚、导出和归档入口。
- 旧内置 Skill 经标准 seed package 一次性迁移，不保留长期 Legacy loader、源码目录 CRUD 或双 Registry。
- A Prompt、B Resources、C Executable 分级验收，不能把“格式可解析”表述为“第三方代码可安全执行”。
- C 级第三方代码只能进入独立 worker/沙箱，不能在 FastAPI 或 Agent 进程内执行。

## 当前实现判定

| 能力 | 当前状态 | 已落地范围 | 剩余边界 |
|------|----------|------------|----------|
| A Prompt | 开发支持已实现，发布门未通过 | 标准解析、安全校验、不可变版本、路由、Prompt 注入和 OpenAPI | 真实 MySQL/API/第三方聊天 E2E 与跨平台证据 |
| B Resources | 有限支持 | 版本绑定只读资源、统一调用预算、前端上传/替换/删除/撤销和增量 `resource_changes` | 跨多次读取的累计 token 预算和真实第三方 B 包聊天 E2E |
| C Executable | 未实现 | 识别并保存 `scripts/`；前端允许 `format_compatible=true`、`runtime_ready=false` 的 C 包禁用安装和管理 | 仍禁止启用或执行；缺少 durable worker、独立 runner/沙箱、依赖构建、lockfile、网络/文件/secret grant、取消与进程树终止 |
| 生命周期/一致性 | 主要开发链路已实现 | draft/import/publish/rollback/export、import `target_revision`、管理员纯 draft catalog、多实例 revision/outbox reconcile、统一 stale `503` | import 仍非 durable job；真实数据库、恢复和跨实例故障演练 |
| 授权/可复现运行 | system/global 闭环已实现 | CapabilityGrant、持久 SkillRunBinding、version/digest/revision/effective grants 固定，以及 private Skill/Tool 和显式 ID 过滤 | per-user scope 和完整真实安全 E2E |
| 单轨退出 | 运行旧路径已退出 | `backend/app/agent/skills` 的 20 个运行文件已删除；静态测试禁回归；seed package 位于 `backend/app/skills/seed_packages` | `SK-5` 整体验收和恢复/跨平台证据仍未完成 |

准确结论是“标准 `SKILL.md` package 的 A 级和有限 B 级开发支持”，不是完整通用或可执行 Skill 平台。本机具备 Node/npm 不能替代 C 级隔离与授权边界。

## 本批已实施范围

- 标准 package parser、统一 ZIP/目录 validator 和恶意 package 防护。
- 内容寻址、checksum 校验、原子完成的不可变 package Storage。
- Skill、Alias、Version、Installation、Import、AuditEvent、CapabilityGrant、SkillRunBinding、RegistryState 和 RegistryEvent 领域模型与 migration。
- draft/import/approve/publish/settings/activate/rollback/archive/export/resource API 与标准管理前端。
- 前端资源上传、替换、删除、撤销和增量变更；保存内容时保留未修改资源。
- private Skill/Tool 与显式 ID 授权过滤、B 资源统一调用预算和确认动作的运行版本固定。
- import `target_revision`、Registry revision/outbox reconcile、落后实例拒绝与统一 `SkillRegistryStaleError` `503`。
- 管理员 catalog 可见纯 draft，普通 catalog 与运行 Registry 不可见未发布内容。
- 标准 seed package、旧运行目录删除和静态禁回归测试。
- OpenAPI、活文档和同主题实施/验证记录同步。

## 下一执行顺序

1. 将 import/validation/publish 移入 durable worker，补齐 lease、幂等、重试、取消、背压、DLQ 和重启恢复。
2. 将 system/global 安装扩展为经过授权的 per-user scope，并补 owner/scope/visibility 的真实数据库测试矩阵。
3. 在统一 Tool 调用次数预算之上增加资源跨多次读取的累计 token 预算。
4. 完成真实 MySQL migration/startup/API lifecycle，以及第三方 A/B package 从导入到聊天资源读取的 E2E。
5. 实施 C 级独立 Node/Python runner/沙箱、依赖锁定、网络/文件/secret grant、取消和进程树强制终止。
6. 完成 Storage 损坏、跨实例收敛、恢复、回滚、跨平台和 clean install 演练，再执行 `SKILL-GATE`。

## 阶段关系

```text
AR-0 + SK-0
  -> AR-1 + SK-1
  -> AR-2/AR-3 prerequisites
  -> AR-4 + SK-2
  -> AR-5 starts with skills/tools/mcp + SK-3
  -> SK-4
  -> AR-6 + SK-5
  -> SKILL-GATE
  -> ARCH-GATE
  -> 7 -> 8 -> 9 -> 10
```

现有代码产物不表示任何 `SK-*` 或 `AR-*` 阶段已经通过完整退出门。工作包 `7-10` 继续保留并冻结。

## 回滚边界

- 数据库结构只通过 Alembic upgrade/downgrade 迁移，不手工改表。
- package 版本不可变；内容回滚通过切换已验证 active version 完成。
- API、前端、Registry、grant/run binding 和 seed 必须按同一合同整体回滚。
- 旧目录不恢复为长期运行权威；回滚只能使用标准 seed/package 与数据库版本指针。
