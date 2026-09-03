# E4 身份与稳定 ID 映射合同

日期：2026-09-02  
状态：实施中  
性质：设计合同  
适用范围：E4 业务对象及其用户、会话、文件、Skill、Chroma/sidecar 关联  
实现状态：合同已冻结，映射器尚未实现；本文件不写入 `migration_maps`

## 1. 不变量

1. 每个 source entity 由 `(source_system, entity_type, source_id)` 唯一标识，并在 `migration_maps` 中只允许一条活动映射。
2. 同一 source key 在重复 dry-run/import 中必须得到同一 canonical UUID；source digest 变化不得覆盖原映射，必须进入 `conflict` 并要求新批次/人工处置。
3. 所有 canonical UUID 使用小写、标准 UUID 字符串和 `CHAR(36)` 语义；任何非规范 UUID、空 ID、控制字符、越界长度或隐式类型转换均拒绝。
4. 目标业务 FK 只能引用已通过映射和目标存在性校验的 UUID；不能用用户名、文件名、MD5、Chroma collection 名或 Redis key 代替 FK。
5. 映射、导入、冲突、跳过和恢复均写入 `audit_events`，带 `migration_id`/`import_id`/`correlation_id`；不记录密码、refresh token、原始 IP 或完整敏感 payload。
6. 映射完成前不删除、覆盖或重命名 source；Chroma、MD5、文件和 Skill Storage 只能作为候选输入，不能反向成为业务权威。

## 2. Source key 规范化

| Source | `source_system` | `entity_type` 示例 | 规范化规则 |
|---|---|---|---|
| E3/Django 用户 | `django` | `user` | ShortUUID 视为大小写敏感的不透明字符串；保留原值，禁止 casefold；E3 用户 UUID 规则见下节 |
| 旧 FastAPI 业务表 | `fastapi_legacy` | `session`/`message`/`note`/`memory`/`knowledge_document`/`model_config` | 字符串 trim；整数 ID 转无前导零十进制；拒绝空值和控制字符 |
| 本地文件/sidecar | `filesystem` | `md5_record`/`image`/`export` | 使用相对根路径 + 文件名/MD5；路径先 containment 校验，再 NFC 规范化；不使用绝对路径 |
| Chroma | `chroma` | `collection`/`embedding`/`metadata_ref` | collection 名和 metadata source 仅作外部引用；不得直接生成业务 FK，必须追溯到 SQL 原文 |
| Skill Storage/Legacy | `skill_storage` 或 `skill_legacy` | `package`/`version`/`run_binding` | 使用 content-addressed digest、版本或旧 ID；digest 必须是小写 SHA-256 |

## 3. Target UUID 规则

### 3.1 已有 canonical UUID

若 source 主键已经是标准 UUID，先转小写并验证版本/格式；只有在目标表不存在冲突且 source digest 一致时才可保留。若同一 UUID 被不同 source key 声称，整批 `conflict`，不得自动合并。

### 3.2 E3 用户映射兼容规则

E3 已冻结的用户映射不可改写：

```text
target_uuid = lowercase(UUID5(NAMESPACE_URL, "django/user/" + source_id))
```

该规则只适用于 `source_system=django, entity_type=user`，必须与既有 `migration_maps` 的 `source_digest` 和 E3 证据一致。业务对象不得复用用户命名空间字符串。

### 3.3 E4 旧业务对象

对没有 canonical UUID 的业务对象，候选规则为：

```text
target_uuid = lowercase(UUID5(NAMESPACE_URL,
  "doki-e4/" + source_system + "/" + entity_type + "/" + normalized_source_id))
```

该 UUIDv5 字符串已由用户确认作为 E4 候选规则；实施时仍须在 fixture 中证明跨类型/跨系统无碰撞。不得以随机 UUID 作为可重放迁移的唯一标识，也不得从文件名/时间戳猜测对象身份。

## 4. Digest 与幂等

- 必须区分三层 digest：`snapshot_manifest_digest`（本批只读 dump/bundle manifest）、`entity_content_digest`（单表/单对象规范化内容）和 `artifact_digest`（原始文件、ZIP 或 canonical archive 字节）。三者均使用 SHA-256 并分别写入证据；`migration_maps.source_digest` 只能承载该映射对应的 entity digest，不能代替批次 manifest 或原始 artifact digest。
- `entity_content_digest` 的输入先按固定字段顺序、UTF-8、UTC 时间和明确 null/空字符串规则规范化，再计算 digest；集合型输入先按 canonical source key 排序，不能依赖数据库自然返回顺序。
- Legacy `md5` 字段/sidecar 值（32 位十六进制）只作为历史内容标识和对账维度，不能填充要求 64 位小写 SHA-256 的 `source_digest`，也不能单独证明用户身份或文件内容未变。
- 集合型 source 必须按 canonical source key 排序后计算集合 digest；不能使用数据库自然返回顺序。
- 同 key + 同 digest：dry-run 返回原 target UUID，导入为 no-op 或明确 `already_mapped`。
- 同 key + 不同 digest：返回 `source_digest_conflict`，保留旧映射，生成冲突报告；禁止覆盖、删除或“最后写入胜出”。
- 不同 key + 同 target UUID：返回 `target_uuid_collision`，整批停止，等待人工决定是否建立显式别名关系。
- 业务唯一约束（例如 `(user_id, md5)`、canonical name、版本号）冲突时，先进入 `conflict`；不能仅凭内容相同跨用户合并。

### 4.1 Legacy ID 兼容与原文保留

- `chat_messages.id` 当前为整数自增键。迁移不得把该值静默替换为 UUID；目标必须保留可查询的 `legacy_message_id`（至少与 `source_system`/`source_session_id` 组成唯一键），并另行生成稳定 canonical message UUID，API 兼容层按显式映射返回旧 ID 或新 ID。
- `chat_sessions.id`、旧 `user_id`、文件名、MD5 和 Chroma collection 名称都只能作为 source key/外部引用，不能互相推断身份或直接充当 canonical FK。

### 4.2 加密配置与媒体表示

- `user_model_configs.api_key_encrypted` 是依赖密钥版本的密文，不能直接复制或把密文当作可验证的业务值。实施前必须确定旧/新 key 的持有者、版本标记、重加密/轮换流程和失败处置；dry-run 只验证可解密性与 digest/版本，不得输出明文 key。
- 当前模型未提供独立的图片/媒体 SQL 表。若 E4 要求把 extracted images 或 avatar 纳入业务权威，必须先批准具体目标表、内容/引用字段、大小上限、digest 和 on-delete 规则；在此之前只能记录文件 manifest 和 orphan，不得把路径字符串冒充已迁移媒体。

### 4.3 与现有 `migration_maps` schema 的兼容门槛

- 当前 E3 `migration_maps` 约束只允许 `mapped`、`conflict`、`error`（见 `backend/app/models/identity_domain.py` 与 `20260828_0003_identity_auth.py`）。本文件的 `candidate`、`validated`、`imported`、`reconciled`、`orphan`、`excluded` 是 E4 流程状态，不能未经 schema 变更直接写入该表。
- 实施前必须明确选择：为流程状态增加受控字段/旁表，或将未持久化的准备状态留在脱敏 inventory、仅在通过校验后写入现有三态映射。无论采用哪种方案，都要保证 source key 唯一、target UUID 不可变、冲突可审计且重复批次可重放。
- `migration_maps` 当前只有一个 `source_digest` 字段；batch manifest digest、entity content digest 和 artifact digest 必须通过新增受控字段/manifest 关联或明确的审计载体分别保存，不能把三者串接/覆盖在同一列。

## 5. 用户/公共 scope

- 用户对象必须先通过 `django/user` 或既有 canonical `users` 映射；未知用户、禁用用户是否允许保留历史数据需用户在实施前确认。
- 公共知识/全局 Skill 不能伪造某个用户 UUID。目标表需要显式 `scope_type=global`/`scope_id=global` 或单独的 owner 语义；在 schema 未确认前不得把 `NULL`、空串或固定用户当作公共 owner。
- Chroma metadata 中缺失用户、使用旧用户标识或跨用户混杂的对象必须列入 `orphan`/`scope_conflict`，不自动归属。

## 6. 映射状态机

```text
candidate -> validated -> mapped -> imported -> reconciled
      \-> conflict / orphan / excluded
```

- `candidate`：仅来自只读 inventory。
- `validated`：source digest、identity、owner scope、唯一性和目标 schema 均通过。
- `mapped`：`migration_maps` 已写入且 immutable。
- `imported`：目标业务行和关联 FK 已在同一迁移批次中成功提交。
- `reconciled`：行数、digest、约束、审计和派生 job 对账通过。
- `conflict`、`orphan`、`excluded` 必须带 `error_detail` 和处置人；除非新批次明确批准，不能自动回到 `mapped`。

## 7. Dry-run 输出

每个 entity type 必须输出：

- source key 总数、可规范化数、重复数、空/非法数；
- candidate UUID、target 已存在数、missing owner 数、FK orphan 数；
- source digest、目标冲突 digest、唯一约束冲突和跨源碰撞；
- 预期新增/更新/no-op/conflict/orphan 行数；
- 脱敏示例（不得输出密码、token、完整 PII 或原始 BLOB）；
- `migration_batch_id`、输入 snapshot manifest、工具版本、schema revision 和 correlation ID。

dry-run 必须是零写入；任何数据库连接、文件写入或 Chroma/Redis 访问都要在证据中明确列出并通过 allowlist。

## 8. 审计与恢复

每个批次至少记录 `migration.started`、`migration.dry_run`、`migration.imported`、`migration.reconciled` 或 `migration.blocked` 事件；事件包含 actor/role、source/target、batch、digest、计数、结果、原因和 correlation ID。

恢复时按 source key 恢复映射和目标快照，不通过重新生成随机 UUID 或删除 source 解决冲突。旧 fencing token、过期 lease 或非当前 batch 的 job 不能提交导入结果。

## 9. 已确认决策与剩余 gate

以下决策已由用户在 2026-09-02 确认并作为实施约束：

- 合法 UUID 保留；否则使用固定 namespace + UUIDv5；E3 `users.id` 复用既有确定性映射。
- unknown/orphan/duplicate/关键 FK、权限、审计和跨域引用问题 fail-closed；非关键问题可 quarantine 并记录交接。
- 用户/Embedding 配置进入 SQL；reranker 保持版本化部署配置；未确认 key-version 前不迁移密文。
- Chroma collection/metadata 用户归属冲突标为 `scope_conflict`，不猜测归属，交 E5。
- 完整 Skill 输入接口、DTO、digest、alias/owner/scope、preview/validate、错误码和幂等合同在 E4 冻结；package 标准化、发布和授权交 E6，E6 不重构输入接口。

以下仍是执行 gate，而不是待用户重新确认的设计问题：

- 公共知识/全局 Skill 的 owner/scope 目标列及无用户对象的处置（需逐表 schema/fixture gate）。
- 已禁用/已删除用户的历史聊天、笔记、知识和 Skill 是否保留、隔离或排除。
- 同 MD5 不同文件名、同文件内容跨用户、Chroma 与 SQL 行数不一致时的处置。
- 整数 message ID 的映射是否采用 UUID5，并如何保留 API 兼容的旧 ID 映射。
- orphan/conflict 的人工审批人、重试批次编号和审计字段（按批次 runbook 填写）。
- `api_key_encrypted` 的旧/新加密 key、版本标记、重加密流程和不可解密配置的处置。
- 图片/avatar 是否进入 SQL 业务权威；若进入，目标媒体表、BLOB/引用格式、大小限制、digest 和删除策略。
- Chroma collection 名称后缀与 metadata/sidecar 用户 ID 不一致时的证明材料和最终 scope 决策（交 E5）。
- batch manifest digest、entity content digest 与 artifact digest 的字段承载及对账报告格式（E4-03 schema gate）。

## 明确未做

- 未生成或写入任何 E4 `migration_maps`。
- 未连接在线 MySQL/Redis/Chroma，未读取 `.env` 作为目标，未执行 dry-run/import。
- 未修改现有主键、FK、唯一约束或业务数据。
- 未在 key-version 确认前迁移任何密文；未把 Chroma/MD5/file 观察写回业务表。
