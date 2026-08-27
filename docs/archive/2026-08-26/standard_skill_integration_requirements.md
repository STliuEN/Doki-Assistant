# 标准兼容 Skill 管理需求规格

状态：A 级和有限 B 级开发支持已形成，尚未通过本地 A/B `SKILL-GATE`；C 级未实现且 `EXEC-SKILL-GATE` 未通过；`PUBLIC-HA-GATE` 未通过

版本：1.2

最近复核：2026-08-26

适用范围：Skill package、Tool/MCP capability、Agent runtime、worker、管理 API 和 Skill 管理前端

本文定义 Doki 全面采用标准兼容 Skill 管理的目标合同。2026-08-26 蓝图确认后，Skill 的最终业务权威是同一个 MySQL 数据库，原始包、manifest 和资源清单进入 SQL；本地目录/ZIP 只作为显式导入输入，旧 Storage/Registry/YAML 只属于迁移期适配。任务由 FastAPI 内置 SQL runner 默认单并发执行；独立进程仅作为未来 C 级插口。该改造是当前架构重写阶段必须执行的最高优先级业务域重构，不再等待 `ARCH-GATE` 后实施。本文把发布判断拆成三个独立门禁：`SKILL-GATE` 只验收本地 A/B 标准 package 能力，`EXEC-SKILL-GATE` 独立验收可执行 C 级能力，`PUBLIC-HA-GATE` 验收公网和高可用部署。`SKILL-GATE` 是本地 `ARCH-GATE` 的组成条件；未声明 C 级支持时，`EXEC-SKILL-GATE` 不是本地 A/B 或 `ARCH-GATE` 的前置。公网部署必须通过 `PUBLIC-HA-GATE`，且只有公网启用 C 级时才额外依赖 `EXEC-SKILL-GATE`。架构底座和 AR 阶段仍以[架构重写计划](../../architecture_rewrite_plan.md)为事实源。当前代码已经具备 A 级和有限 B 级开发支持，但未满足本文完成定义，不能据此声明本地 A/B、可执行 Skill 或公网部署已发布就绪。

本文中的“必须”“不得”是发布阻断要求，“应该”需要在实现偏离时提交 ADR，“可以”是非阻断扩展。

## 0. 当前实现判定

截至 2026-08-25，对“Doki 是否已经支持通用 Skill”的结论是：**部分满足标准包管理和 A/B 级运行条件，不满足完整通用执行条件，也未达到发布门禁。**

| 能力层 | 当前状态 | 已有实现 | 主要阻断项 |
|--------|----------|----------|------------|
| 标准格式与 A Prompt | 开发支持已实现，本地 A/B 发布门未通过 | 标准 frontmatter `SKILL.md` 解析、未知字段保留、ZIP/目录统一校验、不可变版本、Prompt 注入、路由样例和 OpenAPI 生成基础 | Skill import/export/error schema 仍有已知偏差；真实 MySQL/API/第三方聊天 E2E 与当前声明平台的发布证据仍缺失 |
| B Resources | 有限支持 | 资源 manifest、不可变对象存储、版本绑定的按需读取、统一调用预算，以及前端上传/替换/删除/撤销和增量 `resource_changes` | 尚无跨多次读取的累计 token 预算和真实第三方 B 包聊天 E2E |
| C Executable | 未实现，`EXEC-SKILL-GATE` 未通过 | 能识别并保留 `scripts/`；服务端已固定新导入为可审计的 `installed_disabled`，仍禁止启用和执行 | 无 runner/沙箱、Node/Python adapter、lockfile、网络/文件/secret grant、取消和进程树强制终止；C 级仍不可发布 |
| 单轨生命周期 | 主要开发链路已形成，本地 A/B 发布门未通过 | 当前过渡实现仍有 MySQL 领域、content-addressed Storage、draft/import/publish/rollback/export、`target_revision`，以及 revision/outbox、stale `503` 和旧目录静态禁回归的局部实现/单元测试 | 最终目标改为统一 MySQL 原始包/manifest 与 FastAPI 内置 SQL runner；当前 outbox acknowledgement 不是逐 consumer，单实例 fail-closed/重启恢复尚未由真实故障测试证明；多实例收敛属于 `PUBLIC-HA-GATE`；import 仍非 durable worker，Legacy 对账、恢复和 GC 未完成 |
| 授权与可复现运行 | 系统级控制骨架已形成，闭环未证明 | CapabilityGrant、持久 SkillRunBinding、version/digest/revision/effective grants 字段，以及 private Skill/Tool 和显式 ID 过滤的实现/单元测试 | 仅 system/global；角色仍来自旧管理员判定，per-user scope、grant revoke 传播、Tool/MCP policy digest、延迟确认漂移和真实安全 E2E 未完成 |

旧 `backend/app/agent/skills` 的 20 个运行文件已经删除，静态测试禁止重新引入 `skill.yaml` loader/写入路径；标准 seed package 保留在 `backend/app/skills/seed_packages`，不依赖旧运行目录。该删除关闭了旧运行入口，但也提前移除了通用迁移器的在线输入：seed 只代表已知内置基线，不能替代能够保留历史别名、设置、修改内容和 Tool 绑定的 `LegacySkillMigrator`。迁移证据必须从只读备份、最后包含旧目录的 Git 历史导出或发布归档离线重建；不得为补证据恢复 Legacy runtime。管理员 catalog 可以查看尚无 active version 的纯 draft，普通 catalog 与运行 Registry 不可见。

因此当前准确表述是“标准 `SKILL.md` package 的 A 级和有限 B 级开发支持，以及尚待真实环境验证的授权/一致性控制骨架”，不是“任意第三方 Skill 均可安装并安全执行”或“授权闭环已经完成”。`scripts/` 存在不代表 C 级兼容，本机安装 Node/npm 也不能替代独立 runner 和 capability enforcement。

## 1. 已确认决策

1. 弃用当前 `skill.yaml + SKILL.md + 源码目录 Registry` 的内置 Skill 能力。
2. 目标系统只有一种 Skill 内容模型：根目录包含标准 `SKILL.md` 的版本化 Skill package。
3. 前端保留可视化管理能力，包括新建、导入、编辑、配置、验证、启停、升级、回滚、导出和卸载；前端保存的内容也必须是标准兼容 package。
4. 现有 Skill 只通过一次性 `LegacySkillMigrator` 转换为标准 package，不保留长期 Legacy runtime 或双 Registry；seed 安装器不能充当通用迁移器。
5. 所有 Skill 无论来自导入、前端创建、系统初始化或迁移，都经过同一解析、存储、授权、路由和执行链路。
6. 标准包内容采用不可变版本；编辑不是原地覆盖，而是生成新的标准兼容版本并切换 active pointer。
7. Skill 管理和运行不得写入仓库源码目录，不得产生 Git tracked/untracked 运行文件。
8. 第三方脚本不得进入 API 进程；本次 A/B 不执行脚本，未来 C 级才进入受约束的独立进程。
9. 除 AR-0/AR-1 等不可绕过的可靠性前置外，标准 Skill 在业务域、SQL consumer、内置 runner workload 和前端功能迁移中均排第一优先级。

目标链路固定为：

```text
ZIP/directory import ----+
Visual Skill editor -----+--> Standard package validator
System seed package -----+             |
Legacy one-shot migrator +-------------+
                                       v
                              versioned Skill domain
                                       |
                    +------------------+------------------+
                    v                  v                  v
              routing/context    capability grants   isolated runner
```

不存在 `BuiltinSkillRegistry`、`LegacySkillRegistry` 或“前端 Skill 特殊格式”并行运行。

### 1.1 架构绑定

AR/SK 的当前状态、固定执行顺序和四个门禁只在[架构重写计划](../../architecture_rewrite_plan.md)维护。本文只定义 Skill 领域合同和验收项。关键边界是：Skill import/validation/publish 是 SQL durable job 和 FastAPI 内置 runner 的首个业务 consumer；AR-1 负责 SQL job/UoW/lease/fencing/重启合同，独立进程协议和 Node/Python adapter 仅属于可选 SK-4/C 级插口。基础依赖未满足时先补对应 AR 底座，不得转做工作包 `7-10`；C 级与公网/HA 不反向阻断本地 A/B。

## 2. 目标与非目标

### 2.1 目标

- 只有标准 `SKILL.md`、没有 `skill.yaml` 的包可以直接导入、验证和管理。
- 前端可以创建一个全新的标准 Skill，并可视化编辑 frontmatter、Markdown 指令和包内资源。
- 当前内置 Skill 全量转换后，ID/alias、默认选择、Tool 绑定和聊天行为有明确迁移对照。
- 包升级不覆盖安装设置和授权；失败升级不影响当前健康版本。
- 单个坏包或脚本崩溃不影响 API 启动、Registry 健康或其他 Skill。
- Skill 的来源、版本、digest、有效授权和每次运行绑定可审计、可复现。
- Tool/MCP 的解析结果、provider/endpoint 身份、风险与确认策略以 policy digest 固定到每次 Run，策略变化不能被旧确认或旧 binding 绕过。
- 任意有效版本都可以导出为不依赖 Doki 私有 `skill.yaml` 的标准 package。

### 2.2 非目标

- 不承诺无条件运行任意操作系统命令、任意依赖或任意第三方 Skill。
- 不要求标准包携带 Doki 私有 manifest；Doki 管理设置保存在安装域，不污染可导出的上游内容。
- 不在首版开放未经固定 commit/digest 的远程 URL 自动安装。
- 不允许包内声明自行授予网络、文件、密钥、Tool 或高风险操作权限。
- 不为 Skill 新增独立数据库；继续使用目标架构中的统一 MySQL 和内置 SQL runner。旧 canonical Storage 仅作为迁移输入，不是最终业务权威。
- 不在迁移完成后继续扫描 `backend/app/agent/skills` 或接受旧 `skill.yaml` 作为运行时来源。

## 3. 标准 package 合同

### 3.1 最小 package

Skill package 根目录必须包含 UTF-8 `SKILL.md`。文件必须以 YAML frontmatter 开始，并至少提供非空的 `name` 和 `description`：

```markdown
---
name: example-skill
description: Describe when this skill should be selected.
---

# Instructions

Instructions used after the skill is selected.
```

解析要求：

- `name` 保留外部原值并允许连字符；Doki 不得沿用当前只允许下划线的 ID 规则拒绝标准名称。
- Doki 使用内部稳定 UUID 标识 Skill；当前 `memory_read` 等 ID 作为 alias 保留，不再作为文件路径或主键。
- 未识别的 frontmatter 字段必须无损保存在原始 manifest 中，但不能因此获得权限。
- 导入器必须保留原始 `SKILL.md`、结构化解析结果和内容 digest。
- 上游未声明版本时，Doki 仍必须生成不可变内部 revision 和 digest。
- frontmatter 的写回必须使用结构化 YAML 解析器，不能用字符串拼接破坏未知字段。

### 3.2 可选目录

| 路径 | 标准语义 | Doki 行为 |
|------|----------|-----------|
| `references/` | 按需读取的参考资料 | 受路径、类型、大小和 token 预算控制，不整包注入 Prompt |
| `assets/` | 模板、图片或生成所需静态资源 | 只读访问；不能按文件名推断可信性 |
| `scripts/` | 可执行脚本和辅助文件 | 只有 C 级兼容并获授权后才能在独立 worker 执行 |
| `SKILL.md` 相对链接 | 正文到包内资源的引用 | 解析后必须仍位于同一不可变包根目录 |
| 其他文件 | 许可证、依赖锁或宿主扩展 | 默认保存但不赋权；仅由显式 Adapter 解释 |

Doki 可以识别可选扩展 metadata，但标准 A/B 级导入不得依赖扩展文件。C 级执行所需 entrypoint/runtime 可以来自受支持的标准声明，也可以由管理员在安装配置中映射；映射不得回写或伪造上游包。

### 3.3 兼容等级

| 等级 | 能力 | 启用条件 | 对外表述 |
|------|------|----------|----------|
| A Prompt | 解析 frontmatter，命中后加载 `SKILL.md` 正文，不要求 Tool | 格式、授权和上下文预算通过 | A 级标准 Skill 支持 |
| B Resources | A + 受限读取 `references/`、`assets/` | resource manifest、containment 和配额检查通过 | 标准 Skill 指令与资源支持 |
| C Executable | B + 执行批准的 Node/Python entrypoint | 独立 worker、依赖锁定、沙箱、取消和授权全部通过 | 标准 Skill 可执行支持 |
| Incompatible | 格式、平台、runtime、依赖或 capability 不满足 | 不允许启用 | 必须显示具体不兼容原因 |

兼容状态必须拆分为：

- `format_compatible`：包能否正确解析和保存。
- `runtime_ready`：当前部署是否具备运行时、依赖和已批准能力。
- `enabled`：管理员是否已经发布给当前 scope。
- `installed_disabled`：package 和安装记录已持久化但尚未获准运行；可查看、诊断、导出、重新审批或归档，不得路由、设为默认、读取运行资源或执行脚本。

不得把“成功解析”“本机检测到 Node/npm”或“已经安装”展示为“可以安全执行”。

当前前端对 `format_compatible=true` 但 `runtime_ready=false` 的 C 包保留“批准并安装”入口；服务端审批请求无论传入何种 enable/default 参数，均持久化为 `installed_disabled`，并由独立设置变更承担后续启用审计。该状态不得显示启用或执行入口；含 `scripts/` 不会因安装成功而获得运行能力。完整授权、runner 和真实 API/浏览器发布证据仍未完成。

## 4. 单一领域模型

### 4.1 核心实体

| 实体 | 关键字段和职责 |
|------|----------------|
| `Skill` | 稳定 UUID、canonical name、scope、owner、归档状态 |
| `SkillAlias` | 标准名称、现有 Doki ID 和历史别名；alias 在有效 scope 内唯一 |
| `SkillVersion` | 不可变 revision、上游版本、source provenance、parent、digest、Storage key、解析 manifest、验证状态 |
| `SkillInstallation` | scope、active version、enabled、default selected、visibility、order、revision |
| `SkillPolicy` | routable、always-on 授权、正负样例、上下文预算和本地显示/路由设置 |
| `CapabilityRequest` | package 请求的 Tool、资源、脚本、runtime、网络和 secret 能力 |
| `CapabilityGrant` | 管理员批准后的 provider、范围、风险下限、确认策略和资源预算 |
| `RuntimeBinding` | 被批准的脚本/package command、参数 schema、runtime 和依赖环境 |
| `SkillImport` | 上传对象、幂等键、状态、诊断、检查结果和操作者 |
| `SkillResourceManifest` | 相对路径、媒体类型、大小、checksum、用途和可执行标记 |
| `SkillRunBinding` | 每次 Agent Run 固定的 Skill version、digest、registry revision 和有效 grants |

来源只作为 provenance，例如 `import`、`visual_editor`、`system_seed`、`legacy_migration`；来源不得改变解析、授权或执行语义。

### 4.2 不变量

- 所有 active Skill 都必须指向通过统一 validator 的标准 package version。
- 已发布 `SkillVersion` 不可修改；编辑、升级和回滚只创建或切换版本。
- 同一 scope、同一 Skill 同时只能有一个 active version。
- Agent Run 开始后固定 version 和 digest；运行中升级不得改变该 Run。
- `CapabilityRequest` 只能请求能力，不能覆盖 `CapabilityGrant` 或降低系统风险级别。
- package 不能自行设置 `always_on`；只有 Doki 受信策略可以授予。
- 卸载默认停用并归档；存在 Run、审计或保留期引用时不得物理删除。
- Registry 以不可变 revision 发布；单个版本失败只能隔离该版本，不能清空上一健康快照。
- 前端创建的 Skill 与外部导入 Skill 使用相同 schema、validator、Storage 和 runtime。
- active pointer、Installation/Policy/Grant revision、audit 和 outbox 在同一 MySQL 事务提交；Registry 只能消费已提交 revision，不能发布半完成版本。
- grant 撤销必须递增 policy/registry revision，使新 Run 立即 fail closed，并取消或重新授权尚未执行的 job；已运行任务和延迟确认不得继续使用被撤销的 grant。

### 4.3 数据权威

| 数据 | 权威来源 | 派生状态 |
|------|----------|----------|
| Skill 身份、版本元数据、安装、policy、grant、active pointer、审计 | 统一 MySQL schema | 可选内存 catalog；Redis 不参与正确性 |
| 原始归档、规范化 package、正文、资源、lockfile | 统一 MySQL 业务数据 | 内置 runner staging 和临时工作区；本地目录/ZIP 仅为显式输入 |
| 路由向量 | 无独立事实源 | 以 `skill_version_id + digest + embedding_version` 标识的可重建 projection |
| 导入、验证和执行任务 | MySQL durable job/outbox | SSE/polling 进度视图 |

Skill 不得引入第二套业务数据库模型。缓存丢失后必须可从 MySQL 原始包和 manifest 恢复；路由向量损坏时必须从 SQL 原文重建 Chroma projection。

## 5. 前端可视化管理

前端继续使用统一 Skill 管理入口，但页面管理的是标准 package 和安装状态，不再读写私有 `skill.yaml`。

### 5.1 Catalog

- 搜索及状态、兼容等级、scope、provenance 筛选。
- 每项显示名称、版本、状态、兼容等级、作用域、来源摘要和更新时间，不只显示 ID。
- 顶部提供“新建标准 Skill”和“导入标准 Skill”两个入口。
- 不再出现“内置 Skill”“Doki 格式 Skill”或不同 Registry 的切换。
- 未授权用户不显示管理命令，但 API 仍必须执行权限校验。

### 5.2 标准内容编辑器

前端新建和编辑必须支持：

- `name`、`description` 和受支持的 frontmatter 字段。
- 完整 Markdown 指令正文。
- `references/`、`assets/` 的文件上传、替换、删除和受控预览。
- `scripts/` 和依赖/lockfile 的文件树、差异和兼容诊断；是否允许在线编辑脚本可后置，但必须支持包替换。格式兼容但 runtime 未就绪的 C 包允许禁用安装，不允许启用或执行。
- 未识别 frontmatter/文件的保留提示，保存时不得静默丢弃。
- 保存前结构化预览最终 `SKILL.md` 和 package diff。
- 每次保存创建新 version，支持版本说明、比较、激活和回滚。
- 从任意健康版本导出标准目录 ZIP，不包含 Doki 私有管理字段。
- `revision`/ETag 乐观锁；并发覆盖返回可恢复的 `409`。
- 切换 Skill、关闭页面或升级前处理未保存内容，不得静默丢失。

编辑外部导入版本时，系统必须保留原始版本，并创建带 `derived_from_version_id` 的新标准版本；新版本仍可导出和重新导入，不转换成 Doki 私有格式。

### 5.3 管理设置

与 package 内容分离管理：

- enabled、default selected、visibility、scope 和排序。
- routable、路由正负样例和本地显示/路由设置。
- Tool/MCP capability 映射和批准的 runtime、文件、网络与 secret 范围。
- `always_on` 风险说明，只允许具有相应权限的管理员授予。
- smoke test、诊断、版本、审计、升级、回滚和卸载。

这些设置属于 `SkillInstallation/SkillPolicy/CapabilityGrant`，不得偷偷写入 `SKILL.md` 或导出包。

### 5.4 详情视图

| 视图 | 内容 |
|------|------|
| 概览 | 版本、digest、许可证、provenance、状态、兼容结论和诊断摘要 |
| 内容 | frontmatter、Markdown 编辑器、原文和 package diff |
| 资源 | 文件树、类型、大小、checksum、上传和安全预览 |
| 管理设置 | enabled/default/visibility/order、路由策略和 scope |
| 权限与运行时 | capability request/grant、runtime、依赖、网络/文件/secret 范围 |
| 版本 | 历史版本、来源链、更新 diff、激活、回滚和导出 |
| 诊断与审计 | 导入/验证/执行错误、操作人、时间和 correlation ID |

## 6. 角色和授权

| 角色 | 允许操作 |
|------|----------|
| 普通用户 | 查看对其可见且已启用的 Skill；选择本轮候选；查看允许公开的说明和运行诊断 |
| Skill 管理员 | 新建、编辑、导入、配置、启停、升级、回滚、导出和归档 Skill |
| 安全管理员 | 批准脚本、网络、外部命令、高风险 Tool 和 secret reference；撤销 capability grant |
| Worker identity | 只领取已签发、带 version 和 capability scope 的任务；不能修改授权和 active pointer |

后端详情响应必须返回 `allowed_actions`。前端不得根据用户名、页面入口或本地状态推断权限；隐藏按钮只是体验优化。

角色必须分离：Skill 管理员可以准备 package 和安装设置，但不能自批脚本、网络、secret 或高风险 Tool/MCP grant；安全管理员不能在同一审批动作中修改被审批 package。紧急例外必须使用单独权限、短 TTL、双人复核和完整审计。grant 撤销是高优先级安全事件，必须记录操作者、原因、before/after policy digest、受影响 scope/Run/job 和取消结果。

每次执行的有效能力必须是：

```text
package capability request
  intersect administrator grant
  intersect user/tenant policy
  intersect runtime available capability
```

任一层缺失都必须 fail closed 并产生结构化诊断。package 声明、MCP `readOnlyHint` 或前端设置均不能降低系统风险级别、确认或审计要求。

Tool/MCP capability 还必须绑定 `tool_definition_digest`、provider identity、MCP server/config revision、endpoint allowlist digest、风险等级和确认策略 digest。创建 Run 和恢复延迟确认时都重新验证这些 digest；任一漂移均拒绝执行并要求重新审批，不能只按 Tool 名称或显式 ID 授权。

## 7. 导入、验证、发布和回滚

### 7.1 接入入口

首个发布版本必须支持：

- 管理前端上传本地 ZIP。
- 管理 CLI 导入本地目录或 ZIP，使用与 API 相同的 application service 和 validator。
- 前端直接新建标准 package。
- 初始化时从明确的 seed 清单安装标准 package；seed 不得获得特殊运行权限。

Git 固定 commit、可信 Registry 和签名发布放在后续阶段。首版不得接受服务端任意路径，也不得由 API 直接抓取用户输入 URL。

### 7.2 状态机

```text
received/draft -> staged -> validating
                            -> rejected
                            -> quarantined
                            -> review_required -> publishing -> installed_disabled
                                                     |              |
                                                     +-> failed      +-> smoke_tested -> enabled

enabled -> editing/updating -> review_required -> publishing -> enabled(new version)
                           \-> failed (old version remains active)

enabled/installed_disabled -> disabled -> archived
enabled/installed_disabled -> rollback -> previous healthy version
```

要求：

- 上传或大 package 保存返回持久化 job/import ID；页面刷新和 worker 重启后仍能查询进度。
- 相同 scope、provenance 和 digest 的重复请求必须幂等。
- 发布前完成格式、路径、资源、依赖、capability 和平台检查。
- 新安装固定为 `installed_disabled`，不得自动启用或自动成为默认 Skill。
- 权限或依赖相较当前版本扩大时必须重新进入 `review_required`。
- 更新失败保留当前 active version、policy 和 grants，并提供可重试诊断。
- 单个 package 的校验、Storage 损坏、Registry 构建或 smoke test 失败只隔离该 package/version；上一健康版本和其他 Skill 保持可用，禁止因一个坏包发布空的全局 catalog。
- staging object、构建工作区和未引用 finalized object 必须记录 owner/import/job、创建时间和 digest，具备明确 TTL、引用检查、幂等 orphan GC、GC 审计和 dry-run；GC 不得删除被 Version、Import、Run 或保留策略引用的对象。
- 审计、digest 和失败摘要按审计策略保留；不能随 staging GC 一并丢失。

### 7.3 原子发布

发布采用 `stage -> validate -> preflight -> approve -> atomic activate`：

1. 内容先写 staging object，不进入 catalog。
2. Worker 规范化 package，生成 resource manifest、digest 和兼容报告。
3. 管理员确认权限、Tool 映射、scope 和安装设置。
4. Storage atomic finalize 成功后，在同一数据库事务写 Version、Installation、audit 和 outbox。
5. Registry 消费 revision 并切换不可变快照；失败时保留上一快照。

数据库事务失败时 finalized object 进入可对账 orphan 状态而不是进入 catalog；Registry publish 失败时数据库 revision 保持权威、当前进程标记 stale 并继续使用上一健康快照或拒绝新 Run，不得确认半发布成功。active pointer 与 grant/policy revision 必须原子切换，审计和 outbox 缺一不可提交。不得在半写入目录上调用全局 `reload()`，不得长期双写源码目录和数据库。

## 8. Package 验证与供应链边界

默认限制应由部署配置提供，并在 AR-0 用真实 package 复核。首版建议上限：

| 项目 | 默认上限 |
|------|----------|
| 上传归档 | 50 MiB |
| 解压后总大小 | 200 MiB |
| 文件数量 | 2,000 |
| 单文件 | 20 MiB |
| `SKILL.md` | 256 KiB |
| 路径层级 | 20 |
| frontmatter | 64 KiB |

Validator 必须在发布前拒绝：

- `..`、绝对路径、Windows 盘符/UNC、NUL、保留设备名和路径逃逸。
- symlink、junction、hardlink、device、FIFO 和其他非常规文件。
- 大小写折叠后冲突、Unicode 规范化冲突、重复条目和覆盖写入。
- 超限归档、压缩比异常、递归归档炸弹和声明大小不一致。
- 根 `SKILL.md` 缺失、frontmatter 语法错误、必需字段为空或文本编码非法。
- digest 冲突、同版本不同内容，以及不受支持的 runtime/platform。

检查阶段不得执行 `npm install`、`pip install`、生命周期脚本或包内命令。外部依赖解析只能在批准后由隔离构建任务完成。

HTTP/API 门禁必须固定以下结果且进入 OpenAPI、API 测试和前端错误处理：超过上传/解压/文件/正文预算统一返回 `413`，revision、ETag、idempotency key、目标 digest 或审批快照冲突返回可恢复的 `409`，格式/ZIP 结构错误返回稳定的 `4xx + error_code`，不得伪装为 `500`。ZIP 测试至少覆盖 Zip Slip、绝对/盘符/UNC、Unicode/大小写冲突、symlink/junction/hardlink、device/FIFO、重复条目、加密 ZIP、CRC/截断、压缩炸弹和嵌套归档预算。浏览器导入、导出和资源预览只能由明确 CORS allowlist origin 发起；预检、凭据和响应头不得使用通配 origin，跨源失败必须 fail closed。

## 9. 运行时要求

### 9.1 A/B 级运行

- 路由阶段只加载名称、描述、兼容状态和路由 metadata。
- 命中后再加载正文；不得把全部已安装 `SKILL.md` 注入 system Prompt。
- 资源只能通过受限的 `skill_list_resources` 和 `skill_read_resource` 按需读取。
- 资源读取执行 containment、类型、字节、次数和 token 预算；不得返回 Storage 真实路径。
- 没有 Tool 的 A 级 Skill 必须可以正常工作，不能被标记为“能力不可用”。

### 9.2 C 级脚本运行

- AR-1 负责 SQL durable job 领取/租约/fencing、内置 runner、只读 package 与临时输出契约、取消/超时和重启恢复；不以“已支持 C 级 Skill”为退出条件。独立进程协议只作为可选 C 级插口。
- SK-4 在该协议之上实现 Node/Python runtime adapter、锁文件构建、RuntimeBinding 和平台资源限制；Node/Python 代表包与真实恶意包测试只属于 `EXEC-SKILL-GATE`。该分工禁止用 SK-4 的产物反向作为进入 SK-4 所需的 AR-1 前提。
- API 进程不得 `import`、`require` 或直接执行 package 代码。
- 当前 A/B Skill 通过 SQL durable job 进入 FastAPI 内置 runner；runner 崩溃/重启不能丢失 SQL job 或拖垮核心认证。C 级脚本才进入受约束独立进程。
- package 以只读方式挂载，输出写入有配额的临时工作区。
- 禁止把模型生成文本交给 shell 字符串解释；只调用批准的脚本/package command，并以 argv 数组传参。
- 必须限制 wall time、CPU、内存、PID/进程树、磁盘、输出、网络和 secret。
- 取消或超时必须终止整个进程树，并留下确定的 `cancelled`/`timed_out` 状态。
- 默认断网；egress 只允许批准的协议、主机、端口、重定向和 DNS 解析结果。
- secret 使用引用按任务注入，禁止写入 package、Prompt、普通 catalog、日志或构建缓存。
- Node/Python 环境按 package digest 隔离并由 lockfile 复现；无锁定依赖默认不得进入 C 级 ready。
- 本机安装 npm/Node 只能使检查显示 runtime available，不能绕过 worker、授权和沙箱。

无 entrypoint 声明的 C 类 package 可以由管理员选择允许的 `scripts/` 文件或 `package.json` command；选择结果写入 `RuntimeBinding`，不得回写 package。

### 9.3 平台支持声明

当前 backend lock、uv resolution 和 CI 都是 Windows-only；因此本地 `SKILL-GATE` 当前最多声明 Windows A/B 支持，不能把未运行的 Linux/macOS 视为通过。A/B 门禁只要求对 README/兼容矩阵中明确声明的平台提供 clean install、validator、Storage、API/chat E2E 和恶意 package 证据。

`EXEC-SKILL-GATE` 必须逐个平台验收 runner、资源限制和进程树终止。若要声明 Linux 支持，必须先拆分 CPU/GPU 和平台专用依赖、生成并检查 Linux lock/requirements、建立 Windows/Linux CI matrix，再在 Linux 上运行同一 conformance 与真实 Node/Python package E2E；仅让通用 Python 源码可导入不算平台支持。未声明的平台应返回明确 incompatible/platform diagnostics，而不是尝试执行。

## 10. Registry、路由和运行固定

- Registry 从 MySQL active pointers 和不可变 Version 构建快照，不扫描源码目录作为权威。
- 激活事务必须写 outbox；API/worker 通过单调 `registry_revision` 更新并定期对账。
- 单 package 解析失败进入 quarantine，Registry 使用该 Skill 的上一健康版本或禁用该 Skill。
- 路由不得硬编码业务 Skill ID；正负样例和策略来自版本化 metadata/SkillPolicy。
- 无路由信号时不得回退全部 Skill；按用户允许集、风险和上下文预算返回空集或明确兜底。
- catalog metadata、正文、资源和 Tool schema 分层加载，并分别设置数量、字节和 token 预算。
- 每次 Run 记录 `skill_id/version/digest/registry_revision/effective_grants`。

本地 `SKILL-GATE` 要求单实例 worker 在激活/回滚、kill/restart、重复/乱序投递和 lease/fencing 场景中保持确定结果，落后或状态不明时拒绝新 Skill Run。真实多实例 API/worker 在目标时间内收敛到同一 registry revision 的要求属于 `PUBLIC-HA-GATE`；超时实例必须拒绝新 Skill Run，而不是使用混合版本。

## 11. API 合同

### 11.1 规范 API

| 方法与路径 | 用途 |
|------------|------|
| `GET /skills/catalog` | 返回按用户/scope/权限过滤的 catalog |
| `POST /skills/drafts` | 前端新建标准 Skill draft |
| `GET /skills/{id}` | package、安装、策略、兼容和 `allowed_actions` 摘要 |
| `PUT /skills/{id}/draft` | 以 expected revision 保存新的标准 package draft |
| `POST /skills/{id}/publish` | 验证、审批并发布 draft version |
| `POST /skills/imports` | multipart 上传归档，返回 `202 + import_id` |
| `GET /skills/imports/{id}` | 查询进度、manifest、兼容报告、诊断和请求能力 |
| `POST /skills/imports/{id}/approve` | 提交 scope、grants、Tool 映射、安装设置和预期 digest |
| `POST /skills/{id}/smoke-tests` | 启用前执行受限 smoke test |
| `PATCH /skills/{id}/settings` | 修改 Installation/Policy/Grant，不改 package |
| `GET /skills/{id}/versions` | 查询历史版本、provenance、diff 和状态 |
| `POST /skills/{id}/versions/{version}/activate` | 原子切换到已验证版本 |
| `POST /skills/{id}/rollback` | 回滚到指定健康版本 |
| `GET /skills/{id}/versions/{version}/export` | 导出标准 package ZIP |
| `DELETE /skills/{id}` | 停用并归档；物理清理由保留策略和 GC 控制 |

所有写操作，以及导入拒绝、验证失败、审批、grant 授予/撤销、Tool/MCP policy 漂移、smoke test、执行/取消/超时、GC、恢复和越权拒绝，都必须产生不可变审计。审计至少包含 actor/actor role、scope/owner、source/package/policy/tool-provider digest、before/after revision、grant diff、correlation/run/job/import ID、来源 IP/客户端摘要、结果/error code 和时间；secret、token 和资源正文必须脱敏。API schema 必须进入 OpenAPI，前端类型由合同生成或自动校验，不能继续使用 `Any` catalog/detail 响应。

### 11.2 现有 API 退出

当前 `POST/PUT /skills` 的私有 `SkillPayload` 和直接写目录语义必须退出：

1. 先为旧响应、Skill 选择和编辑主流程建立 characterization tests。
2. 前端在同一迁移窗口切换到 draft/publish/settings API。
3. 旧 URL 可在一个明确版本窗口返回兼容视图和 deprecation header，但不得继续写 `skill.yaml`。
4. 观察期结束后删除旧 payload、文件写入和递归目录删除代码。
5. `/chat/skills` 必须认证并按用户、scope、visibility 和 grant 过滤，不返回未授权 Tool 指令。

## 12. 旧内置能力迁移与退出

### 12.1 一次性迁移映射

| 当前来源 | 标准目标 |
|----------|----------|
| 目录名和 `skill.yaml.id` | `SkillAlias`，保留现有聊天/API 引用 |
| `label/description` | 标准 `SKILL.md` frontmatter 的 `name/description` |
| 现有 `SKILL.md` 正文 | 移除/合并旧 frontmatter 后成为标准正文 |
| `tools` | `CapabilityRequest` 和待批准 Tool binding |
| `default/visibility/order` | `SkillInstallation` |
| `always_on/routable/routing_examples` | `SkillPolicy`；always-on 必须重新授权 |
| Git 跟踪目录 | 迁移输入和回滚快照，不再作为运行时权威 |

### 12.2 迁移步骤

1. 对现有目录做只读 inventory、checksum 和旧 API/UI/路由 characterization tests；若工作树中的旧目录已经删除，输入必须来自只读备份、最后含旧目录的 Git commit 导出或已保存发布 artifact，且记录来源 commit/artifact digest。
2. 实现一次性、可离线运行的通用 `LegacySkillMigrator`，输出与外部导入完全相同的标准 package 和领域记录；它必须处理真实 legacy 内容和设置，不能把当前 seed 清单当作迁移完成证明。
3. 短暂冻结 Skill 管理写入，按 digest 幂等迁移所有现有 Skill；逐项对账 ID/alias、正文/资源 checksum、Tool/MCP binding、default/visibility/order、always_on/routable/routing examples、owner/scope 和启用状态。
4. 影子比较新旧 catalog、alias、Tool、默认选择、Prompt 和路由结果。
5. 一次切换 Registry 读权威和前端写权威；旧目录只作为受控回滚快照。
6. 观察期通过后删除运行时 Legacy loader、旧 CRUD 和硬编码 Skill 路由；归档或删除旧目录由独立变更计划列出明确清单。
7. CI 增加静态检查，禁止重新引入 `skill.yaml` loader、源码目录写入或双 Registry。

迁移器不是长期 Adapter，也不得在正常启动时运行。回滚只切换已演练的 Registry/active pointer 和只读快照，不恢复双写，也不得为了找回迁移输入重新启用 Legacy loader、CRUD、Registry 或 `skill.yaml` runtime。

当前代码状态只完成旧 loader/CRUD 删除和静态禁回归切片，尚未完成最终运行权威切换：`backend/app/agent/skills` 的 20 个运行文件已删除，标准 seed package 位于 `backend/app/skills/seed_packages`。这是提前删除而不是完整迁移证据：seed 不能证明用户修改、历史别名、安装设置和 Tool/MCP binding 已逐项保留。必须从只读历史输入补做离线通用迁移、差异报告和批准记录；无法取得的字段必须明确记为不可恢复并由负责人批准，不能静默用 seed 默认值覆盖。完整迁移对账与真实环境恢复仍属于 `SK-5` 本地 A/B 门禁；跨平台只按第 9.3 节的声明平台验收。

### 12.3 必须删除的旧行为

- 启动时扫描 `backend/app/agent/skills/*/skill.yaml`。
- 管理 API 直接创建、覆盖或递归删除源码目录。
- 通过进程内单例 `reload()` 发布全局 Skill 状态。
- 因 Skill 无 Tool 而判定其不可用。
- 在路由代码中硬编码业务 Skill ID 或无信号时暴露全部 Skill。
- 让第三方/本地 Skill 代码通过 `importlib` 进入 API 进程。

Tool 与 MCP 可以继续作为 capability provider，但不能继续决定 Skill package 格式或获得绕过授权的直连入口。

## 13. Skill 工作包交付索引

本表只标识 Skill 领域产物；阶段状态、完整依赖和执行队列以[架构重写计划](../../architecture_rewrite_plan.md)为准。

| 工作包 | Skill 领域交付 | 架构依赖摘要 |
|--------|----------------|--------------|
| SK-0 | 格式 ADR、A/B/C 矩阵、资源上限、Legacy inventory、characterization、威胁与恶意包 fixtures | 与 AR-0 同步关闭合同和 P0 |
| SK-1 | parser、validator、领域骨架、manifest 接口，并把 import/validation 接入 SQL durable job | AR-1 SQL job；持久化遵守 AR-3 schema |
| SK-2 | MySQL 原始包/资源生命周期、draft/import/publish/export/rollback 和可视化管理 | AR-3 业务数据权威 |
| SK-3 | A/B Prompt/Resources、预算、Tool/MCP policy binding、per-user 和真实聊天 E2E | AR-2/AR-3 权限权威与 AR-5 首域 |
| SK-4 | 可选 Node/Python adapters、锁定环境、RuntimeBinding、沙箱和强制终止 | AR-2/AR-5 与 SK-3；不阻断 A/B |
| SK-5 | A/B 原子切换、MySQL/Chroma 恢复、离线 Legacy 对账、单轨观察和收口 | AR-4 RAG 恢复与 SK-3；SK-4 不是前置 |

## 14. 验收矩阵

### 14.1 标准格式与单轨约束

- 只有标准 frontmatter `SKILL.md`、名称含连字符的 fixture 可导入，不需要 `skill.yaml`。
- 前端新建、编辑并导出的 Skill 可被重新导入，内容和未知字段无损。
- A 级纯指令 Skill 无 Tool 也能启用和参与路由。
- 带 `references/assets` 的 package 只按需读取，不整包进入 Prompt。
- 重复 digest 导入幂等；同版本不同 digest 被阻断并要求人工决策。
- 代码和 CI 中不存在运行时 Legacy Registry 或 `skill.yaml` 写入路径。
- 所有 provenance 类型走相同 validator、Storage、Registry、授权和运行时。
- 超限请求稳定返回 `413`；revision/digest/idempotency/审批快照冲突稳定返回可恢复 `409`；恶意或损坏 ZIP 返回结构化 `4xx` 且不产生 active version。
- 新安装（尤其含 `scripts/` 或 runtime 未就绪的包）只进入 `installed_disabled`，catalog、默认选择和 Agent 路由均不能把它当作可运行 Skill。

### 14.2 可视化管理

- 管理员可新建、导入、完整编辑指令、管理资源、配置、验证、启停、升级、回滚、导出和卸载。
- 保存产生新 revision；旧 version 可查看和回滚。
- 两个管理员并发保存不会静默覆盖；页面离开不会静默丢失内容。
- package 内容与管理设置分别保存，导出不携带 Doki 私有字段或 secret。
- 权限或依赖扩大时 UI 强制重新审核，不能一键静默更新。
- 任何 UI 操作后 `git status --short` 不新增或修改 Skill 运行文件。

### 14.3 旧 Skill 迁移

- 只读备份、历史 Git 导出或发布 artifact 的来源和 digest 可追溯；seed package 不作为通用迁移完成证明。
- `LegacySkillMigrator` 对当前全部 Skill 的 alias、正文/资源、Tool/MCP binding、默认状态、visibility、排序、scope/owner 和路由样例逐项产生迁移对照和 checksum。
- 新旧影子 catalog 与 Prompt 在批准的兼容范围内一致；差异有显式批准记录。
- 迁移中断可续跑，重复执行幂等；切换失败可回到只读快照。
- 观察期后启动和运行不读取旧目录；删除一个旧目录不影响新 Registry。
- 旧前端/API 写入已删除或返回明确 deprecation/unsupported，不会重建 `skill.yaml`。
- 无法从只读历史输入恢复的字段有显式不可恢复报告和负责人批准；不得恢复 Legacy runtime 或用 seed 默认值静默覆盖。

### 14.4 安全、隔离与授权

- 路径穿越、绝对/盘符路径、symlink/junction/hardlink、大小写冲突和压缩炸弹在发布前被拒绝。
- 普通用户看不到管理动作，直接越权调用返回 `403`。
- 用户显式提交 Skill/Tool ID 仍不能绕过 visibility、scope 和 capability grant。
- package 不能降低高风险确认；未批准网络、文件、命令或 secret 访问均被拒绝。
- Skill 管理员与安全管理员职责分离；grant revoke 使新 Run、排队 job 和延迟确认 fail closed，并留下完整影响审计。
- Tool/MCP definition、provider/endpoint、风险和确认 policy digest 在 Run/确认恢复时一致；任一漂移触发重新审批。
- A/B 验证 worker kill 后任务进入确定状态并可恢复，旧 fencing token 不能发布结果。这是 `SKILL-GATE` 条目。
- 无限循环、内存耗尽、超量输出、派生进程和取消测试会终止整个 C 级任务，API 保持 ready。这是 `EXEC-SKILL-GATE` 条目，不阻断 A/B。

### 14.5 一致性和可观测性

- 单实例 API/worker 在 kill/restart、重复/乱序、lease 过期和 fencing 场景中恢复到确定 revision；落后或状态不明时拒绝新 Skill Run。这是 `SKILL-GATE` 条目。
- 多 API/worker 实例的 consumer offset、跨实例 revision 收敛和部署拓扑恢复属于 `PUBLIC-HA-GATE`，不得用本地替身作为通过证据。
- 每次 Run 可查询固定 Skill version、digest、effective grants、Tool/MCP policy digest 和 correlation ID。
- 新建、导入、拒绝、验证、批准、编辑、激活、回滚、grant 授予/撤销、停用、导出、执行、取消、GC 和恢复全部产生第 11.1 节定义的审计。
- 缓存丢失后 catalog 可从 MySQL 原始包/manifest 恢复；单 package 损坏不影响其他 Skill。
- active pointer、policy/grant revision、audit 和 outbox 原子提交；数据库或 Registry 发布失败不会暴露半完成版本，上一健康快照保持可用。
- staging TTL、引用保护、orphan GC dry-run/执行/审计测试通过，GC 不删除受引用对象。
- OpenAPI、后端 unit/API/integration、前端 component/E2E、CORS、`409/413`、恶意 ZIP/package 和所有声明支持平台的 conformance 测试进入 CI。当前 Windows-only lock/CI 只能支持 Windows 声明；增加 Linux 声明前必须满足第 9.3 节。

### 14.6 C 级代表性验收

本节全部属于 `EXEC-SKILL-GATE`，不属于本地 A/B `SKILL-GATE`。必须在每个声明支持的平台使用至少一个真实 Node/npm 和一个 Python 标准 Skill package 完成端到端验收：导入、`installed_disabled`、检查、角色分离审批、依赖构建、实际执行、产物校验、grant revoke、取消、超时和回滚。还必须用恶意测试包验证网络/文件/secret 拒绝、无限循环、资源耗尽、派生进程和进程树终止。只解析 `SKILL.md`、检测到本机 Node/Python 或通过 AR-1 语言无关测试桩不算 C 级通过。

## 15. 完成定义

发布声明按门禁分开，不能用一个含糊的“支持标准 Skill”覆盖不同安全边界：

- `SK-0/1/2/3/5` 与第 14.1 至 14.5 节除明确标为 `PUBLIC-HA-GATE` 的多实例条目外，其余 A/B 条目通过 `SKILL-GATE` 后，才能对已经实际验收的平台声明“A 级标准 Skill 支持”或“标准 Skill 指令和资源支持”。
- `SK-4` 与第 14.6 节在某个平台通过 `EXEC-SKILL-GATE` 后，才能对该平台声明“标准 Skill 可执行支持”；未通过的平台继续显示 incompatible，未通过时 C 包只能 `installed_disabled`。
- `SKILL-GATE` 通过后可成为本地 `ARCH-GATE` 的有效证据；`EXEC-SKILL-GATE` 不阻断本地 A/B 或本地产品解锁。
- 只有 `PUBLIC-HA-GATE` 通过后才能声明公网/HA 就绪；公网只提供 A/B 时不依赖 `EXEC-SKILL-GATE`，公网启用 C 时二者都必须通过。
- 当前内置 Skill runtime、旧写入 API 和源码目录 Registry 已退出，不存在长期双轨。
- 可视化管理覆盖内容、安装、版本、授权和诊断，并能导出标准 package。
- 兼容矩阵公开列出未支持的 runtime、权限和 package 结构。
- 主 README、开发文档、OpenAPI、管理员指南、Security threat model、变更记录和测试记录已同步。

在对应门禁通过前，当前能力的准确表述是“Windows 上标准 `SKILL.md` package 的 A 级和有限 B 级开发支持，以及包含 CapabilityGrant/RunBinding/private 过滤骨架的预注册 Tool/MCP 编排”；这些控制尚未形成真实环境授权闭环，不得表述为已发布的本地 A/B、Linux/macOS 支持、通用可执行 Skill 或公网/HA 支持。
