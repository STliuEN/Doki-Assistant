# 标准兼容 Skill 管理需求规格

状态：需求已更正并细化，尚未实施

版本：1.1

最近复核：2026-08-24

适用范围：Skill package、Tool/MCP capability、Agent runtime、worker、管理 API 和 Skill 管理前端

本文定义 Doki 全面采用标准兼容 Skill 管理的目标合同。该改造是当前架构重写阶段必须执行的最高优先级业务域重构，不再等待 `ARCH-GATE` 后实施；它必须先通过 `SKILL-GATE`，而 `SKILL-GATE` 是 `ARCH-GATE` 的组成条件。架构底座、依赖顺序和总门禁仍以[架构重写计划](./architecture_rewrite_plan.md)为唯一事实源；本文不表示当前代码已经支持标准 Skill。

本文中的“必须”“不得”是发布阻断要求，“应该”需要在实现偏离时提交 ADR，“可以”是非阻断扩展。

## 1. 已确认决策

1. 弃用当前 `skill.yaml + SKILL.md + 源码目录 Registry` 的内置 Skill 能力。
2. 目标系统只有一种 Skill 内容模型：根目录包含标准 `SKILL.md` 的版本化 Skill package。
3. 前端保留可视化管理能力，包括新建、导入、编辑、配置、验证、启停、升级、回滚、导出和卸载；前端保存的内容也必须是标准兼容 package。
4. 现有 Skill 只通过一次性迁移器转换为标准 package，不保留长期 Legacy runtime 或双 Registry。
5. 所有 Skill 无论来自导入、前端创建、系统初始化或迁移，都经过同一解析、存储、授权、路由和执行链路。
6. 标准包内容采用不可变版本；编辑不是原地覆盖，而是生成新的标准兼容版本并切换 active pointer。
7. Skill 管理和运行不得写入仓库源码目录，不得产生 Git tracked/untracked 运行文件。
8. 第三方脚本不得进入 API 进程，只能在受约束的独立 worker 中运行。
9. 除 AR-0/AR-1 等不可绕过的可靠性前置外，标准 Skill 在业务域、Storage consumer、worker workload 和前端功能迁移中均排第一优先级。

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

### 1.1 优先级与门禁关系

“最高优先级”不表示跳过 worker 隔离、事务、Storage、权限或恢复要求，而是表示每项基础能力具备后，第一个落地和验收的业务消费者必须是标准 Skill：

```text
AR-0 + SK-0 contract/baseline
  -> AR-1 runtime foundation + SK-1 parser/domain skeleton
  -> AR-2/AR-3 identity, audit and schema prerequisites
  -> AR-4 canonical Storage + SK-2 package lifecycle
  -> AR-5 starts with skills/tools/mcp + SK-3 A/B runtime and visual management
  -> SK-4 executable runner
  -> AR-6 + SK-5 cutover and legacy removal
  -> SKILL-GATE
  -> ARCH-GATE
  -> work packages 7-10
```

如果 Skill 专项的依赖未满足，应优先补齐对应 AR 底座，不得改做工作包 `7-10`。如果 Skill 专项验收失败，`ARCH-GATE` 不得通过。

## 2. 目标与非目标

### 2.1 目标

- 只有标准 `SKILL.md`、没有 `skill.yaml` 的包可以直接导入、验证和管理。
- 前端可以创建一个全新的标准 Skill，并可视化编辑 frontmatter、Markdown 指令和包内资源。
- 当前内置 Skill 全量转换后，ID/alias、默认选择、Tool 绑定和聊天行为有明确迁移对照。
- 包升级不覆盖安装设置和授权；失败升级不影响当前健康版本。
- 单个坏包或脚本崩溃不影响 API 启动、Registry 健康或其他 Skill。
- Skill 的来源、版本、digest、有效授权和每次运行绑定可审计、可复现。
- 任意有效版本都可以导出为不依赖 Doki 私有 `skill.yaml` 的标准 package。

### 2.2 非目标

- 不承诺无条件运行任意操作系统命令、任意依赖或任意第三方 Skill。
- 不要求标准包携带 Doki 私有 manifest；Doki 管理设置保存在安装域，不污染可导出的上游内容。
- 不在首版开放未经固定 commit/digest 的远程 URL 自动安装。
- 不允许包内声明自行授予网络、文件、密钥、Tool 或高风险操作权限。
- 不为 Skill 新增独立数据库；继续使用目标架构中的统一 MySQL、canonical Storage 和独立 worker。
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

不得把“成功解析”“本机检测到 Node/npm”或“已经安装”展示为“可以安全执行”。

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

### 4.3 数据权威

| 数据 | 权威来源 | 派生状态 |
|------|----------|----------|
| Skill 身份、版本元数据、安装、policy、grant、active pointer、审计 | 统一 MySQL schema | Redis catalog/revision cache |
| 原始归档、规范化 package、正文、资源、lockfile | canonical Storage，不可变对象 | worker staging 和临时工作区 |
| 路由向量 | 无独立事实源 | 以 `skill_version_id + digest + embedding_version` 标识的可重建 projection |
| 导入、验证和执行任务 | MySQL durable job/outbox | SSE/polling 进度视图 |

Skill 不得引入第四种数据库模型。Redis 丢失后必须可从 MySQL 和 Storage 恢复 Registry；路由向量损坏时必须可重建。

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
- `scripts/` 和依赖/lockfile 的文件树、差异和兼容诊断；是否允许在线编辑脚本可后置，但必须支持包替换。
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

每次执行的有效能力必须是：

```text
package capability request
  intersect administrator grant
  intersect user/tenant policy
  intersect runtime available capability
```

任一层缺失都必须 fail closed 并产生结构化诊断。package 声明、MCP `readOnlyHint` 或前端设置均不能降低系统风险级别、确认或审计要求。

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
- staging 具备 TTL 和受控 GC；审计、digest 和失败摘要按审计策略保留。

### 7.3 原子发布

发布采用 `stage -> validate -> preflight -> approve -> atomic activate`：

1. 内容先写 staging object，不进入 catalog。
2. Worker 规范化 package，生成 resource manifest、digest 和兼容报告。
3. 管理员确认权限、Tool 映射、scope 和安装设置。
4. Storage atomic finalize 成功后，在同一数据库事务写 Version、Installation、audit 和 outbox。
5. Registry 消费 revision 并切换不可变快照；失败时保留上一快照。

不得在半写入目录上调用全局 `reload()`，不得长期双写源码目录和数据库。

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

## 9. 运行时要求

### 9.1 A/B 级运行

- 路由阶段只加载名称、描述、兼容状态和路由 metadata。
- 命中后再加载正文；不得把全部已安装 `SKILL.md` 注入 system Prompt。
- 资源只能通过受限的 `skill_list_resources` 和 `skill_read_resource` 按需读取。
- 资源读取执行 containment、类型、字节、次数和 token 预算；不得返回 Storage 真实路径。
- 没有 Tool 的 A 级 Skill 必须可以正常工作，不能被标记为“能力不可用”。

### 9.2 C 级脚本运行

- API 进程不得 `import`、`require` 或直接执行 package 代码。
- 脚本通过 durable job 进入独立 worker runner；worker 崩溃不能拖垮 core API。
- package 以只读方式挂载，输出写入有配额的临时工作区。
- 禁止把模型生成文本交给 shell 字符串解释；只调用批准的脚本/package command，并以 argv 数组传参。
- 必须限制 wall time、CPU、内存、PID/进程树、磁盘、输出、网络和 secret。
- 取消或超时必须终止整个进程树，并留下确定的 `cancelled`/`timed_out` 状态。
- 默认断网；egress 只允许批准的协议、主机、端口、重定向和 DNS 解析结果。
- secret 使用引用按任务注入，禁止写入 package、Prompt、普通 catalog、日志或构建缓存。
- Node/Python 环境按 package digest 隔离并由 lockfile 复现；无锁定依赖默认不得进入 C 级 ready。
- 本机安装 npm/Node 只能使检查显示 runtime available，不能绕过 worker、授权和沙箱。

无 entrypoint 声明的 C 类 package 可以由管理员选择允许的 `scripts/` 文件或 `package.json` command；选择结果写入 `RuntimeBinding`，不得回写 package。

## 10. Registry、路由和运行固定

- Registry 从 MySQL active pointers 和不可变 Version 构建快照，不扫描源码目录作为权威。
- 激活事务必须写 outbox；API/worker 通过单调 `registry_revision` 更新并定期对账。
- 单 package 解析失败进入 quarantine，Registry 使用该 Skill 的上一健康版本或禁用该 Skill。
- 路由不得硬编码业务 Skill ID；正负样例和策略来自版本化 metadata/SkillPolicy。
- 无路由信号时不得回退全部 Skill；按用户允许集、风险和上下文预算返回空集或明确兜底。
- catalog metadata、正文、资源和 Tool schema 分层加载，并分别设置数量、字节和 token 预算。
- 每次 Run 记录 `skill_id/version/digest/registry_revision/effective_grants`。

多实例激活或回滚后，健康 API/worker 应在 5 秒内收敛到同一 registry revision；超时实例必须拒绝新 Skill Run，而不是使用混合版本。

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

所有写操作必须产生 actor、scope、source digest、before/after revision、grant diff、correlation ID 和结果审计。API schema 必须进入 OpenAPI，前端类型由合同生成或自动校验，不能继续使用 `Any` catalog/detail 响应。

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

1. 对现有目录做只读 inventory、checksum 和旧 API/UI/路由 characterization tests。
2. 实现一次性 `LegacySkillMigrator`，输出与外部导入完全相同的标准 package 和领域记录。
3. 短暂冻结 Skill 管理写入，按 digest 幂等迁移所有现有 Skill。
4. 影子比较新旧 catalog、alias、Tool、默认选择、Prompt 和路由结果。
5. 一次切换 Registry 读权威和前端写权威；旧目录只作为受控回滚快照。
6. 观察期通过后删除运行时 Legacy loader、旧 CRUD 和硬编码 Skill 路由；归档或删除旧目录由独立变更计划列出明确清单。
7. CI 增加静态检查，禁止重新引入 `skill.yaml` loader、源码目录写入或双 Registry。

迁移器不是长期 Adapter，也不得在正常启动时运行。回滚只切换已演练的 Registry/active pointer 和只读快照，不恢复双写。

### 12.3 必须删除的旧行为

- 启动时扫描 `backend/app/agent/skills/*/skill.yaml`。
- 管理 API 直接创建、覆盖或递归删除源码目录。
- 通过进程内单例 `reload()` 发布全局 Skill 状态。
- 因 Skill 无 Tool 而判定其不可用。
- 在路由代码中硬编码业务 Skill ID 或无信号时暴露全部 Skill。
- 让第三方/本地 Skill 代码通过 `importlib` 进入 API 进程。

Tool 与 MCP 可以继续作为 capability provider，但不能继续决定 Skill package 格式或获得绕过授权的直连入口。

## 13. 当前必做实施序列

| 序号 | 工作包 | 核心交付 | 依赖与退出门 |
|------|--------|----------|--------------|
| SK-0 | 合同、威胁与迁移基线 | 格式 ADR、A/B/C 矩阵、资源上限、旧目录 inventory、API/UI/路由 characterization、恶意 package fixtures | 与 AR-0 同步；合同和现状 checksum 评审通过 |
| SK-1 | 标准解析器与统一领域骨架 | `SKILL.md` parser、标准 validator、领域 schema、alias/version/install/policy/grant、Registry snapshot 接口 | AR-1 启动 parser/接口；持久化部分等待 AR-3 schema 规则，不接管流量 |
| SK-2 | Package 生命周期与可视化管理 | canonical Storage、draft/import/validate/publish/export、版本 diff/回滚、前端统一管理页、OpenAPI 类型 | AR-4 Storage 合同通过；UI 保存可重新导入且不写 Git |
| SK-3 | A/B 级运行与一次性迁移 | Prompt/Resources 渐进加载、预算、Tool/MCP capability、旧 Skill 幂等转换、影子 catalog/route 对比 | AR-5 首个业务域；A/B、安全和现有行为门通过 |
| SK-4 | C 级隔离执行 | Node/Python 环境、lockfile 构建、RuntimeBinding、网络/文件/secret 权限、取消/硬终止、smoke test | AR-1 runner/资源隔离成熟；真实 Node package E2E 通过 |
| SK-5 | 原子切换与旧能力退出 | active pointer 切换、多实例 revision、canary/rollback、删除 Legacy loader/CRUD/硬编码路由、运行文档 | AR-6 故障演练；观察期无回退且回滚证据完整 |
| SKILL-GATE | 标准 Skill 总验收 | 本文第 14 节全部阻断项、迁移对账、恢复、跨平台、安全和文档证据 | 必须先于 `ARCH-GATE` 通过 |

### 13.1 与 AR 阶段的绑定

- AR-0 不得退出，除非 SK-0 已完成。
- AR-1 的首个隔离 worker workload 和 durable job conformance consumer 是 Skill validation/runner。
- AR-2 必须提供 Skill 管理员、安全管理员、scope 和审计 actor。
- AR-3 的统一 schema/UoW 必须包含 Skill 领域，不允许先写临时第四数据库或本地 JSON。
- AR-4 的首个 canonical Storage 业务 consumer 是 Skill package，先验证 staging/finalize/checksum/GC 再迁移复杂 knowledge。
- AR-5 的后端第一个业务域是 `skills/tools/mcp`，前端在 auth/shared 基础后首先迁移 Skill 管理。
- AR-6 必须包含 SK-5 的 revision、runner、Storage、权限撤销和 legacy removal 演练。

`SK-0` 是当前下一执行项；`SK-1` 至 `SK-5` 按依赖推进。工作包 `7-10` 在 `SKILL-GATE` 和 `ARCH-GATE` 均通过前继续冻结。

## 14. 验收矩阵

### 14.1 标准格式与单轨约束

- 只有标准 frontmatter `SKILL.md`、名称含连字符的 fixture 可导入，不需要 `skill.yaml`。
- 前端新建、编辑并导出的 Skill 可被重新导入，内容和未知字段无损。
- A 级纯指令 Skill 无 Tool 也能启用和参与路由。
- 带 `references/assets` 的 package 只按需读取，不整包进入 Prompt。
- 重复 digest 导入幂等；同版本不同 digest 被阻断并要求人工决策。
- 代码和 CI 中不存在运行时 Legacy Registry 或 `skill.yaml` 写入路径。
- 所有 provenance 类型走相同 validator、Storage、Registry、授权和运行时。

### 14.2 可视化管理

- 管理员可新建、导入、完整编辑指令、管理资源、配置、验证、启停、升级、回滚、导出和卸载。
- 保存产生新 revision；旧 version 可查看和回滚。
- 两个管理员并发保存不会静默覆盖；页面离开不会静默丢失内容。
- package 内容与管理设置分别保存，导出不携带 Doki 私有字段或 secret。
- 权限或依赖扩大时 UI 强制重新审核，不能一键静默更新。
- 任何 UI 操作后 `git status --short` 不新增或修改 Skill 运行文件。

### 14.3 旧 Skill 迁移

- 当前全部 Skill 的 alias、Tool、默认状态、排序和路由样例都有迁移对照和 checksum。
- 新旧影子 catalog 与 Prompt 在批准的兼容范围内一致；差异有显式批准记录。
- 迁移中断可续跑，重复执行幂等；切换失败可回到只读快照。
- 观察期后启动和运行不读取旧目录；删除一个旧目录不影响新 Registry。
- 旧前端/API 写入已删除或返回明确 deprecation/unsupported，不会重建 `skill.yaml`。

### 14.4 安全、隔离与授权

- 路径穿越、绝对/盘符路径、symlink/junction/hardlink、大小写冲突和压缩炸弹在发布前被拒绝。
- 普通用户看不到管理动作，直接越权调用返回 `403`。
- 用户显式提交 Skill/Tool ID 仍不能绕过 visibility、scope 和 capability grant。
- package 不能降低高风险确认；未批准网络、文件、命令或 secret 访问均被拒绝。
- 无限循环、内存耗尽、超量输出、派生进程和取消测试会终止整个任务，API 保持 ready。
- worker kill 后验证/执行任务进入确定状态并可恢复；旧 fencing token 不能发布结果。

### 14.5 一致性和可观测性

- 多 API/worker 实例在目标时间内收敛到相同 revision；落后实例拒绝新 Skill Run。
- 每次 Run 可查询固定 Skill version、digest、effective grants 和 correlation ID。
- 新建、导入、批准、编辑、激活、回滚、停用、导出和执行全部产生审计。
- Redis 丢失后 catalog 可从 MySQL/Storage 恢复；单 package 损坏不影响其他 Skill。
- OpenAPI、后端 unit/API/integration、前端 component/E2E、恶意 package 和 Windows/Linux conformance 测试进入 CI。

### 14.6 C 级代表性验收

必须使用至少一个真实 Node/npm 标准 Skill package 完成端到端验收：导入、检查、权限批准、依赖构建、实际执行、产物校验、取消、超时和回滚。只解析 `SKILL.md` 或检测到本机 Node 不算 C 级通过。

## 15. 完成定义

只有满足以下条件才能在 README 中声明“支持标准 Skill”：

- SK-3 的 A 级验收完成时只能声明“A 级标准 Skill 支持”。
- SK-3 的 B 级验收完成时可以声明“标准 Skill 指令和资源支持”。
- SK-4、跨平台和安全验收全部通过后，才能声明“标准 Skill 可执行支持”。
- `SKILL-GATE` 已通过并成为 `ARCH-GATE` 的有效证据。
- 当前内置 Skill runtime、旧写入 API 和源码目录 Registry 已退出，不存在长期双轨。
- 可视化管理覆盖内容、安装、版本、授权和诊断，并能导出标准 package。
- 兼容矩阵公开列出未支持的 runtime、权限和 package 结构。
- 主 README、开发文档、OpenAPI、管理员指南、Security threat model、变更记录和测试记录已同步。

在此之前，当前能力的准确表述仍是“Doki 私有 Skill 配置、Prompt 注入及预注册 Tool/MCP 编排”。
