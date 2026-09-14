# E6/E7 共同接口、数据与验收合同

本文件固定联合实施合同；历史入口盘点保持时间边界。2026-09-15 已按本合同完成收口，当前状态及证据见 [closure-review.md](./closure-review.md)。

## 数据与权威

| 对象 | 已有位置 | 目标合同 / migration 注意点 |
|---|---|---|
| 原始包 | 磁盘 objects ZIP；`SkillPackageUpload.raw_archive` 表为空 | 原始新上传字节及 SHA 保存在 SQL；迁移仅能标记 legacy canonical ZIP 输入，不追造旧上传原件 |
| 规范包 | `SkillPackage.canonical_archive/manifest_json/package_digest` 空表；`SkillVersion.storage_key` 指向磁盘 | 复用 SQL schema，新增 version/import 明确 FK；规范 ZIP 与 package digest 各自校验，资源路径/内容 hash 可复算；稳定 UUID 不变 |
| manifest / capabilities | SkillVersion JSON、SkillCapabilityGrant | manifest 保留未知 frontmatter 不解释；requested 与 approved 分离；同 version 不同 digest 拒绝，不自动选 winner |
| grants / RunBinding | E3 AuthorizationGrant、SkillRunBinding、registry revision | 持久化 grant ID/policy revision/subject revision/digest/expiry；按 owner/scope 实时校验；registry cache 不能独立授予能力 |
| media | SQL media_assets 已有、0 行；image endpoints 仍文件读 | 每条 media 绑定 canonical owner/source、MIME/length/content digest/bytes；旧 MD5 URL 仅 SQL 映射，文件路径不成为授权依据 |
| 原文/笔记/聊天 | E4 BusinessSession 与 SQL 原文已存在 | 复用稳定 ID/审计/outbox，补齐媒体和工具路径，不重复迁移已对账原文 |
| legacy map | E4 migration_maps 314 行、SkillAlias 10 行 | 新 batch/namespace 明确 source locator/digest→stable UUID；保留永久映射，不复活 legacy runtime 或把 alias 当权限 |
| 本地文件 | objects、extracted_images、md5 sidecar、seed packages | 只作明确导入/导出/debug 操作输入；关闭通道后 SQL 故障不自动读文件；旧文件保留 |

schema 改动采用 additive migration，新 revision 在实现时按仓库当前 head 分配。先 backfill＋对账，再加必要 not-null/FK/唯一约束；不得为了绕过旧不可变字段而覆写旧 digest、ID 或历史审计。

## 调用合同

- 生产 SQL 包 repository 提供 store_raw、store_canonical、load_verified、read_resource、export；全部接受当前 DB/UoW，资源读取必须携带版本和期望 digest。解析器纯逻辑可复用，磁盘 storage 只用于显式导入导出。
- ZIP 与目录统一校验根 SKILL.md、frontmatter、总字节/文件数/压缩比、Unicode/大小写路径冲突、traversal、symlink/junction、重复条目；不执行脚本、不安装依赖。
- 新导入固定 installed_disabled。内容管理的 publish 不能隐式产生独立安全 grant。有效启用同时要求 ready 包、同一版本/内容/策略 revision 的 approved grant、匹配 scope；approve/revoke 继续角色分离和四眼。
- 新 Run、queued job、普通工具、资源读取、延迟确认和恢复后的执行都核对 current SQL grant/binding；revoke/expiry/改版及时拒绝后续副作用。一次快照通过不能无限授权运行中的工具。
- 错误保持结构化：未授权 401/403，owner 不匹配按既有不可枚举合同，digest/revision 冲突 409，超限 413，unsupported 能力有明确码，SQL/包权威不可用 fail-closed。RAG 维持 E5 degraded/503。
- 文件下载/图片/batch image 校验 owner→source→media；正文/MIME/长度匹配；跨用户引用、缺 source、删除 source、文件同名/同 MD5、损坏 bytes 全部拒绝。空旧媒体不能替代正例测试。
- 显式 debug/import/export 开关默认开发开启、可关闭，事件包含 actor/scope/reason/before/after/digest/correlation；严禁数据库故障 fallback。

## 重点代码接入点

| 范围 | 路径 |
|---|---|
| 包解析与存储 | `backend/app/skills/package.py`、`storage.py`、`service.py`、`seed.py`、`seed_manifest.py` |
| SQL 基础 | `backend/app/models/projection_domain.py`、`skill_domain.py`、`e4_migration.py:MediaAsset` 及 Alembic；`backend/app/e2/skill.py` 仅 synthetic 基础参考 |
| 身份/权限 | `backend/app/auth/authorization.py`、`utils/auth_utils.py`、`router/skill_router.py` |
| 运行绑定 | `backend/app/services/agent_run_service.py`、`confirmation_service.py`、`agent/tool_guard.py`、`skills/resource_tools.py`、`skills/registry.py` |
| 业务与媒体 | `backend/app/router/knowledge_router.py`、`knowledge_service.py`、`note_router.py`、`chat.py`、`services/knowledge_document_service.py`、`db/business_authority.py` |
| 前端 | `front/src/pages/SkillManager.tsx`、`KnowledgeBase.tsx`、`NoteEditor.tsx`、`AIChat.tsx`、`features/chat` |
| 运行与证据 | 独立 E6E7 guard/ops、批次 manifest、dry-run/迁移/restore reports；不可只改 E5 DSN 或复用过期 preflight |

## 固定验收矩阵

| ID | E6/E7 共同退出要求 | 判据 |
|---|---|---|
| JV01 | 空库/恢复库 additive schema、FK、包/media counts/digest | 孤儿/未解释差异 0；失败事务无已发布/已启用结果 |
| JV02 | 目录/ZIP/恶意包/并发幂等/同版本冲突/导出重导入 | 同 digest 稳定 ID；坏包/危险能力不 ready/不执行；原始及规范 digest 可复算 |
| JV03 | 角色分离、请求/批准/撤销/过期/漂移 | 自批/越权/过期 grant 放行 0；新 Run/job/资源/确认均 fail-closed；完整审计 |
| JV04 | legacy 10 包＋aliases/安装/MD5 对账 | 全部稳定 ID 可追溯；新导入 disabled，旧 enabled 不自动变安全授权；不丢失旧事实 |
| JV05 | 图文 SQL、下载/batch/解析/owner/source | 副本真实媒体正例＋跨用户/删除/同 MD5/损坏负例；仅 SQL 恢复后仍可访问 |
| JV06 | Skill→知识/笔记/聊天/SSE/确认链 | UI/API/SQL/job/binding 一致，工具副作用正确归属；中途撤销无后续越权 |
| JV07 | SQL/包/Chroma/文件断路，重启/取消/lease | 核心认证边界可用；失败无文件 fallback，重启不恢复已撤销权限，E5 active 不污染 |
| JV08 | SQL-only restore＋全新 Chroma/无旧 objects/media 目录 | 原始包/资源/图文/配置/授权审计全部恢复；RAG counts/digest 一致 |
| JV09 | 全量回归、前端 build、浏览器、docs/diff | 最终代码相关及全量通过，真实/替身边界清楚，new-api 观察不变 |

105 项为历史准备基线，不能单独作为 JV 通过依据；最终验收使用下列新增执行证据。

## 最终验收矩阵（2026-09-15）

| ID | Result | Evidence and boundary |
|---|---|---|
| JV01 | `pass` | 新空库 Alembic 到 0010，42 表 SQL 恢复摘要一致，新增包/媒体关联 FK 与所有 active version 的 package 引用核验 |
| JV02 | `pass` | 真 SQL 并发幂等、幂等键冲突、恶意 ZIP 隔离、原始/规范/资源摘要及导出重导入；目录/版本冲突/生命周期细分边界由回归覆盖 |
| JV03 | `pass` | 双角色自批仍 403、普通用户拒绝、不同账号批准；enabled 正向控制后的过期/摘要漂移拒绝；撤销传播至 Run/tool/resource/job/confirmation |
| JV04 | `pass` | 10 个稳定 Skill/version/package/legacy map 逐项一致；10 uploads 为 legacy_canonical，目标 imports=0；现为 8 enabled/2 unsupported |
| JV05 | `pass` | 真实 SQL 字节的带图 Markdown，经生产 ingest、下载/batch、跨 owner/同 MD5/删除/损坏校验；目标夹具全部回滚；仅 SQL 恢复仍可读取 |
| JV06 | `pass` | 已授权工具真实写笔记并形成带 Run 来源的 SQL job；本机 qwen3:0.6b 实际调用时间工具，SSE、消息、session、RunBinding 一致；首轮父会话与跨用户回归通过 |
| JV07 | `pass` | 隔离 SQL 停止/固定端口重启，恢复后身份与图像可用；恢复后的 revoked Run 仍拒绝；SQL 包损坏/空 Chroma 拒绝且无文件 fallback；lease/cancel 由全量回归覆盖 |
| JV08 | `pass` | 带媒体/资源/授权审计的 SQL dump 恢复到新卷，无旧 objects/media；真实 embedding 重建新 Chroma，逐条检查 ID/正文/元数据/向量维数 |
| JV09 | `pass` | 最终回归、真实管理员 API/浏览器与授权面板、静态检查、文档/摘要索引通过；new-api 前后相同 |

联合结果 `closed`，完整证据映射与限制见 closure-review.md。历史 0 图片不构成缺口；合成输入、真实服务/SQL、本机模型与单元替身明确区分。C/scripts/外部 MCP、E8 及全局门禁继续冻结。
