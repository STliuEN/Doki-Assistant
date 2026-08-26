# 标准 Skill 核心重构计划

日期：2026-08-24

复核日期：2026-08-25

状态：当前停留在 `AR-0 + SK-0`；Skill 发布安全仍有 P0/P1 阻断。A 级和有限 B 级只有开发切片，C 级执行未实现；`SKILL-GATE`、`EXEC-SKILL-GATE`、`ARCH-GATE` 和 `PUBLIC-HA-GATE` 均未通过。

关联记录：同目录 `change-log.md`、`test-record.md`。两者记录原批次实现与离线回归，不构成阶段退出或发布门禁证据。AR/SK 阶段、依赖和门禁的唯一事实源是 `docs/architecture_rewrite_plan.md`。

## 审阅结论

当前计划的主要问题不是“还缺若干增强项”，而是把局部代码切片写成了已经闭环：

- publish/activate/rollback 在切换 active pointer 前没有重新读取 Storage 并校验 package digest，`ready` 和 `enabled` 不能证明可运行对象仍然完整。
- Registry 有 revision/outbox 代码，但任一损坏 package 仍可使整个运行快照变成 degraded 空集；同 revision 的 reconcile 不会拒绝该快照。隔离复现得到 `publish_status=ready`、`publish_enabled=true`、`registry_degraded=true`、`runtime_skills=0`。
- CapabilityGrant 和 SkillRunBinding 只形成部分数据面。系统没有 Skill 管理员与安全管理员分权、独立 grant 审批/撤销，也没有把普通 Tool/MCP definition 与 policy digest 固定到可复现运行。
- 审计和 API/OpenAPI 合同存在明确缺口，不能写成“授权闭环”“一致性闭环”或“OpenAPI 已完成”。
- 旧运行目录删除只是提前落地的清理切片；固定 seed installer 只覆盖已知系统包，不能替代 Legacy inventory、通用离线迁移、影子对账、观察期和恢复演练。

因此，准确表述只能是：仓库已经形成标准 `SKILL.md` package 的 parser、管理主路径、A 级和有限 B 级桥接等开发切片，但尚未形成可发布、可恢复、可审计的 A/B 单轨 Skill 平台，更没有通用 C 级可执行 Skill。

## 背景与固定决策

Doki 原有 Skill 使用私有 `skill.yaml + SKILL.md`、源码目录写入和进程内 Registry，不能直接承载只有标准 `SKILL.md` 的第三方 package，也缺少不可变版本、授权、回滚和隔离执行合同。

本重构继续遵守以下方向：

- 所有来源统一为根目录包含标准 `SKILL.md` 的版本化 package。
- MySQL 保存 Skill、版本、安装、policy、grant、运行绑定和审计事实；仓库外 Storage 保存 canonical immutable objects。
- 前端覆盖新建、导入、审批、编辑、资源、配置、版本、权限、诊断、回滚、导出和归档，但前端限制不能替代服务端不变量。
- 旧 Skill 通过与外部 import 相同 validator/Storage/domain 链的通用离线迁移器一次性迁移；不恢复长期 Legacy loader、源码目录 CRUD 或双 Registry。
- A Prompt、B Resources、C Executable 分级验收；“格式可解析”不等于“可发布”，“保存了 `scripts/`”不等于“第三方代码可安全执行”。
- C 级代码只能进入独立 worker/runner/沙箱，不得在 FastAPI 或 Agent 进程内执行。

## 当前实现判定

| 领域 | 已有开发切片 | 项目现实与阻断 |
|------|--------------|----------------|
| Package/validator | 标准 frontmatter、指令和资源解析；ZIP/目录统一校验；路径穿越、链接、名称碰撞、体积和压缩炸弹等防护 | `SK-0` 的正式格式 ADR、威胁模型、资源上限、第三方 fixtures 和声明平台 conformance 证据未齐 |
| Storage/版本 | content-addressed archive、checksum、临时写入和原子 finalize；领域中保存 version/digest/storage key | publish/activate/rollback 未在 active pointer 切换前重验 Storage；缺 staged key TTL、引用状态、orphan/final object 对账和 quarantine/GC；内容对象去重与 version/source provenance 尚未清晰分离 |
| A Prompt | 标准正文可进入路由和 Prompt 注入链；已有离线单元/集成切片 | 受发布原子性、Registry 健康、授权、审计和真实 MySQL/API E2E 阻断，不能判定“已实现”或可发布 |
| B Resources | 资源绑定 immutable version，只读渐进加载；前端支持上传、替换、删除、撤销和增量 `resource_changes`；与 Tool 共用单轮调用次数预算 | 缺跨多次读取的累计 token/byte 预算、真实第三方 B 包聊天 E2E 和故障/越权恢复证据 |
| C Executable | parser 能识别并保存 `scripts/`；UI 能显示 `format_compatible=true`、`runtime_ready=false` 的包 | 没有 durable worker、Node/Python adapter、依赖锁定、RuntimeBinding、沙箱、网络/文件/secret grant、取消和进程树终止；必须保持不可启用、不可执行 |
| 生命周期/UI | draft/import/approve/publish/settings/activate/rollback/archive/export/resource API 与管理 UI 主路径存在；import 有 `target_revision` | import/validation/publish 仍在请求路径；服务端未固定新导入为 `installed_disabled`，一步启用主要依赖前端自律；缺 durable job、重启恢复和真实数据库事务证据 |
| Registry/一致性 | revision、RegistryEvent/outbox、reconcile、stale error 和运行 snapshot 代码切片存在 | 单包失败会污染全局快照并丢失上一健康内容；same-revision degraded 可绕过 `503`；degraded/失败事件的 ack 语义和每实例 consumer offset 不完整，不能声明多实例闭环 |
| 授权/RunBinding | CapabilityGrant 模型、private Skill/Tool 与显式 ID 过滤、Skill version/digest/revision/effective grants 绑定存在 | 只有单一 admin；settings 会自动覆盖 grant，缺独立 approve/revoke API、理由和有效期；普通 Tool/MCP policy 仍来自本地源码/YAML且只 reload 当前进程，RunBinding 未固定其 definition/policy digest |
| 审计 | 部分 lifecycle 写操作会创建 AuditEvent | 成功 import 无审计；rollback 仅以 `version_activated` 记账；缺 scope、source/version digest、grant diff、result 和贯穿 request/job/event 的稳定 correlation ID |
| API/OpenAPI/CORS | Skill 路由、response schema、静态 OpenAPI 产物和漂移检查基础存在 | import 幂等冲突未稳定映射 `409`；`413` 覆盖不完整；ZIP export 被声明为 JSON；存在虚假全局 `200 Any`；CORS 未允许 `Idempotency-Key`，不能声明合同准确 |
| 迁移/单轨退出 | 标准 seed packages、已知系统包 installer、旧运行目录删除和静态禁回归测试存在 | 无只读 Legacy checksum inventory、通用 `LegacySkillMigrator`、用户自定义 Skill 零数据证明、新旧 catalog/Prompt/route 影子对账、观察期和恢复演练；目录删除不等于 `SK-5` 完成 |

## 本批实际已实施范围

以下内容可以作为后续工作的已有切片复用，但不得据此跳过前置阶段：

- 标准 package parser、ZIP/目录 validator 和恶意 package 防护测试。
- content-addressed package Storage、checksum 校验和原子 finalize 基础。
- Skill、Alias、Version、Installation、Import、AuditEvent、CapabilityGrant、SkillRunBinding、RegistryState 和 RegistryEvent 领域模型及 migration。
- draft/import/approve/publish/settings/activate/rollback/archive/export/resource API 和标准管理前端主路径。
- 资源上传、替换、删除、撤销、增量修改及未修改资源保留。
- A 级 Prompt 注入与有限 B 级只读资源桥接，以及单轮 Tool 调用次数预算。
- private Skill/Tool 和显式 ID 过滤、部分 grant/run binding 数据面。
- import `target_revision`、Registry revision/outbox/reconcile 和 stale `503` 的局部机制。
- 管理员可见纯 draft、普通 catalog/运行 Registry 隐藏未发布内容。
- 固定 seed packages、旧运行目录删除和静态禁回归测试。
- 静态 OpenAPI 生成与离线回归基础；这只证明产物可生成，不证明当前 schema 和错误合同准确。

## 本批未覆盖范围

本批实现和既有回归不覆盖以下结论：

- 不覆盖安全的 publish/activate/rollback、健康 Registry snapshot 或多实例消费闭环。
- 不覆盖完整 RBAC、grant 审批/撤销、Tool/MCP 版本化权威、可复现 RunBinding 或完整写审计。
- 不覆盖准确的 `409/413`、ZIP media type、CORS 和 OpenAPI 合同。
- 不覆盖通用 durable worker/UoW、真实 MySQL/Redis/Storage 集成、重启恢复、故障矩阵和跨平台 conformance。
- 不覆盖 per-user scope、B 资源累计预算、第三方 A/B 从导入到真实聊天的 E2E。
- 不覆盖通用 Legacy 迁移、影子对账、clean install、Storage/Registry 重建或 `SK-5`。
- 不覆盖 C 级构建和执行；本机存在 Node/npm 或 Python 不能替代隔离、授权和声明平台证据。
- 不覆盖公网部署、多实例运营、canary、HA、PITR 或灾难恢复。

## 下一执行顺序

### 1. 先关闭 `SK-0 / AR-0` 发布安全阻断

在以下事项完成前，publish/activate/rollback 和新导入启用必须 fail closed，不得用继续扩展功能代替止血：

1. publish/activate/rollback 在提交 active pointer 前重新读取 Storage，校验 object、size 和 digest；pointer 与 version/install/outbox 状态按明确 UoW 原子提交，失败保留上一健康版本。
2. Registry 逐包加载和隔离失败；任一坏包不得清空其他 Skill 或覆盖上一健康 snapshot。same-revision degraded 必须拒绝运行并稳定返回 `503`。
3. degraded/失败 reconcile 不得 ack 为成功；补每实例 consumer offset、重放、幂等和乱序语义，明确何时允许推进 revision。
4. 服务端固定新 import 为 `installed_disabled`；approve/publish 与 enable 分离，C 包无论请求参数如何都不得启用。
5. 把 immutable content object 的 digest 去重与 Skill version、source/provenance、审批事实分离；同 upstream version 不得静默接受不同 digest。
6. 冻结 Skill 管理员/安全管理员分权、独立 grant approve/revoke、理由、有效期和 fail-closed 合同；实现完成前禁止把内容发布权限等同于高风险授权权限。
7. 将 Tool/MCP definition 与 policy 迁入版本化权威事实；变更必须产生 Registry revision，RunBinding 固定 definition/policy digest，不能只 reload 单实例本地 YAML/源码。
8. 补全 import、approve、publish、activate、rollback、settings、grant/revoke、export、archive/uninstall 审计，统一 actor、scope、source/version digest、grant diff、result 和 correlation ID。
9. 修正 import 幂等 `409`、体积限制 `413`、ZIP export media type、错误 envelope、`Idempotency-Key` CORS 和 OpenAPI；删除虚假全局 `200 Any`。
10. 为 Storage staging 增加 TTL、引用状态、orphan/final object reconciliation、quarantine 和引用感知 GC，并覆盖 DB commit/finalize 各类部分失败。
11. 完成 `SK-0` 格式 ADR、A/B/C 兼容矩阵、package 威胁模型、资源上限、Legacy checksum inventory 和 API/UI/Prompt/route characterization。

其中角色、权威 schema 和完整审计的最终归属仍分别受 `AR-2/AR-3` 退出门约束；当前 P0 要求是先冻结合同并关闭可绕过路径，不能在控制面未完成时继续宣称发布安全。

### 2. 再建立 `AR-1 + SK-1` 通用可靠性底座

- 实现通用 durable job schema、独立 worker runtime、UoW/outbox 同事务、lease/heartbeat/fencing、幂等、重试、取消、背压、DLQ、人工重放和重启恢复。
- 以 Skill import/validation/publish 作为第一个真实 consumer；API 只提交和查询 job，不在请求内读包、校验和发布。
- 建立语言无关的 `IsolatedProcessRunner` 合同与恶意测试桩；此阶段不实现 Node/Python package adapter。
- 在进入本阶段前，`SK-0/AR-0` 的发布安全、威胁模型、inventory、characterization 和真实依赖基线必须通过。

### 3. 按依赖完成本地 A/B 单轨

1. `AR-2/AR-3`：完成身份收敛、管理员分权、grant revoke、完整审计、统一权威 schema，以及 Skill/Tool/MCP policy 的版本化事实。
2. 在进入后续 package/runtime 切换前完成 per-user scope 与 B 资源累计预算，并纳入 owner/scope/visibility/grant 的真实数据库矩阵。
3. `AR-4 + SK-2`：完成 Storage staging/finalize/TTL/GC/reconciliation、激活前重验、package 生命周期和恢复工具。
4. `AR-5 + SK-3`：完成真实 MySQL/API/第三方 A/B E2E、通用 `LegacySkillMigrator` 和新旧行为影子对账。
5. `SK-5`：完成 Legacy inventory 或可验证零数据报告、幂等迁移、逐项对账、单包损坏隔离、Registry/Storage 重建、回滚、clean install 和观察期。
6. 证据齐全后依次执行本地 A/B `SKILL-GATE` 与 `ARCH-GATE`；此前工作包 `7-10` 保持冻结。

### 4. C 级和公网/HA 保持独立可选轨

- 只有在 `AR-1/AR-2/AR-4/SK-3` 前置合同通过且明确需要 C 级后，才实施 `SK-4` Node/Python adapters、依赖锁定、RuntimeBinding、沙箱和进程树终止，并单独执行 `EXEC-SKILL-GATE`。
- 只有在 `ARCH-GATE` 通过且有明确部署决策后，才进入 `AR-6`，验证公网、多实例、canary、HA/PITR 和 DR，并执行 `PUBLIC-HA-GATE`。
- C 级和公网/HA 不再阻断本地 A/B 单轨与本地产品队列，但未通过各自门禁时不得对外宣称支持。

## 阶段关系

本批执行顺序派生自 `docs/architecture_rewrite_plan.md`，若总计划调整，以该事实源为准：

```text
AR-0 reliability contract and P0 containment
  + SK-0 Skill contract, threat model and baseline
  -> real MySQL/Redis/Storage/Chroma integration baseline
  -> AR-1 generic durable jobs/UoW/process protocol + SK-1 parser/domain skeleton
  -> Skill import/validation/publish as the first worker consumer
  -> AR-2 identity consolidation
  -> AR-3 recoverable relational migration
  -> per-user scope and cumulative resource budgets
  -> AR-4 canonical storage and index projection + SK-2 package lifecycle/UI
  -> AR-5 starts with skills/tools/mcp + SK-3 A/B runtime and migration
  -> SK-5 A/B reconciliation, recovery and single-track closeout
  -> SKILL-GATE
  -> ARCH-GATE
  -> unlock local-only 7-10

optional executable track after AR-1/AR-2/AR-4/SK-3
  -> SK-4
  -> EXEC-SKILL-GATE

optional public/HA track after ARCH-GATE and deployment decision
  -> AR-6
  -> PUBLIC-HA-GATE
```

## 门禁拆分

| 门禁 | 验收边界 | 不包含 |
|------|----------|--------|
| `SKILL-GATE` | 本地标准 A/B package 的生命周期、发布安全、授权、审计、恢复、迁移对账、clean install 和声明平台 conformance | C 级代码执行；公网部署和 HA 运维 |
| `EXEC-SKILL-GATE` | 可选 C 级 Node/Python 构建与隔离执行、资源限制、网络/文件/secret 权限、取消、超时、进程树终止和声明平台 CI/E2E | 不阻断本地 A/B `SKILL-GATE` |
| `ARCH-GATE` | 本地档位 `AR-0` 至 `AR-5` 的架构退出证据和 `SKILL-GATE`；通过后才解冻本地工作包 `7-10` | C 级执行；公网 canary、HA/PITR/DR |
| `PUBLIC-HA-GATE` | 明确部署拓扑下的公网、多实例消费/收敛、canary、容量、监控、HA、PITR、restore-forward 和灾难恢复 | 不作为本地单实例 A/B 产品开发的前置门 |

代码级 revision、故障隔离、offset 和 fencing 不因公网门禁后置而放宽：只要相关多实例代码保留在主路径，就必须在 `SKILL-GATE` 前满足 fail-closed 和可恢复不变量；`PUBLIC-HA-GATE` 负责真实部署拓扑与运营证据。

## 回滚边界

- 数据库结构只通过 Alembic upgrade/downgrade 迁移，不手工改表；任何真实数据迁移先做只读 inventory、备份 manifest 和恢复验证。
- package content object 不可变；只有重新读取 Storage 并验证 digest 后，才能通过 active pointer 切换版本。验证失败保持上一健康 pointer 和 snapshot。
- Registry rebuild/reconcile 失败必须保留上一健康快照并进入可诊断 degraded 状态，不得以空快照和相同 revision 冒充成功。
- API、UI、Registry、policy、grant、RunBinding、audit 和 seed/migrator 必须按同一合同回滚；跨阶段数据变化采用 restore-forward，不假设只切回旧进程即可恢复。
- 旧目录不恢复为长期运行权威；回滚依赖只读 legacy artifacts、迁移 manifest、标准 package 旧版本、Storage/Registry 重建和数据库指针。
- C 级 capability 可独立保持关闭；未通过 `EXEC-SKILL-GATE` 时，不以任何回滚或兼容开关启用 package 代码执行。
- 若任一 P0 不变量或恢复证据缺失，停止在 `AR-0 + SK-0`，不进入 durable worker 之后的完成度声明。
