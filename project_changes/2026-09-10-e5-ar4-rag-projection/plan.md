# E5/AR-4/S4 SQL 原文与 Chroma RAG projection

- 日期：2026-09-10
- 状态：执行批次完成，关闭验收待补充
- 负责人：Codex
- 审阅/批准人：用户
- 用户确认：Q1-Q7 已全部确认；Q1/Q2 按建议，Q3 选择全量迁移且不考虑旧访问性，Q4-Q7 全部按建议执行。2026-09-14 开始实施。

## 1. 当前结论与范围

E4 已于 2026-09-10 经用户批准关闭，关闭证据为 [e4-closure-20260910.json](../2026-09-02-e4-ar3-business-migration/artifacts/e4-closure-20260910.json)。本轮发现主计划、蓝图和交接手册仍停留在 E4 实施中，已依据该记录同步为 E4 已关闭、E5 待你确认。

E5 原先只有[交接手册](../../docs/architecture-execution-handoff-2026-08-26.md)的阶段概要。本文件补充实施顺序、依赖、故障合同、验收证据和未决设计。Q1-Q3 已确认，按用户隔离 generation、区分索引/查询配置，并从 canonical SQL 执行首次全量重建，迁移期间不维持旧 RAG 访问。尚未回答的执行分支保留待决，设计确认不作为已实现事实。

- 目标：SQL 保存原文、业务 metadata、声明式配置、generation 指针和任务状态；Chroma 承载可从 SQL 重建的知识与笔记检索投影。
- 复用：E2 SQL UoW/job/单并发 runner、E3 canonical 身份与审计、E4 canonical 业务写入与投影任务。
- 交付：RAG port、Chroma adapter、配置合同、generation 生命周期、重建与清理任务、既有 API/UI 的真实异步状态、真实依赖恢复证据。
- E6 Skill 规范化、E7 全面业务回接/遗留输入清理、E8 移除 Django/Redis 和最终部署继续按各自阶段执行。E5 只调整实现本阶段检索和配置合同所必需的既有调用方。
- 单机、低并发、一个 MySQL 业务库、runner 并发 1；不增加第二套向量后端或 SQL 向量 BLOB。
- 用户已要求全部 E 阶段结束验收后统一清理中间材料。本阶段保存旧输入、恢复材料和历史证据；运行期新建投影的回收合同见下文，不能把它扩大解释为旧目录删除许可。

## 2. 入口与事实基线

| 项目 | 事实或要求 | 本轮判定 |
|---|---|---|
| Git | 准备前 HEAD `a2d7381`，提交说明 `e4结束`，工作树干净 | 已只读核验 |
| E4 关闭 | 本机业务迁移、源冻结、FastAPI 切流、恢复和故障矩阵已记录并经用户批准 | 历史证据，不等于本轮 live 复验 |
| SQL | E4 记录 target/restore 为 `20260905_0008_e4_business_shadow`、39 表 | 实施前重新核验实例身份、schema 和权限 |
| 投影任务 | E4 知识/笔记/embedding 任务等待 E5 消费 | 实施前只读盘点任务种类、数量、revision、重试状态 |
| 旧输入 | E4 已排除一个原件缺失的测试 PDF；旧 Chroma 的用户作用域冲突留给 E5 | 不从向量或 sidecar 反推原始文档，不把 excluded 项重建回来 |
| 环境 | Python/依赖元数据可读；E4 target/restore/Redis 容器 Exited (255)，应用与 Ollama 端口未监听 | 只读进程/端口观察；无数据库连接、模型调用或 Chroma 打开/写入 |
| 恢复 | E4 manifest、dump 和 restore-forward 可供设计复用 | E5 变更前必须产生自身恢复点并在独立目标验证 |

历史证据来源：[E4 计划](../2026-09-02-e4-ar3-business-migration/plan.md)、[E4 运行说明](../../backend/ops/e4/README.md)。E4 的许可、短时 preflight 和进程状态不能自动成为 E5 实施参数。

## 3. 审查发现

| ID | 严重性 | 发现与影响 | 处理 |
|---|---|---|---|
| F1 | 高 | 主文档仍写 E4 实施中，与已提交关闭记录冲突，执行入口会判断错误 | 已同步三份主文档；历史 E4 时间线保留 |
| F2 | 高 | SQL 完成校验 lease/fence，但 Chroma 的 to_thread 写入不会因 handler 取消而停止；projector 接口也未传递 fencing context | E5-02/04/05 隔离 generation/attempt 写入，并在当前 fence 下提交激活、任务成功和回收需求 |
| F3 | 高 | 原概要把索引变化与查询参数变化混在一起，generation 用户范围未冻结 | Q1/Q2 已确认并修订蓝图：每用户/index_kind 独立；仅索引配置触发重建，代码待实施 |
| F4 | 高 | 原文重建后 mark_indexed 未比较内容 revision/digest，generation 激活只验证 head/scope/ready，无法发现构建期间原文更新/删除 | Q3 已接受首次全量迁移期间 RAG 不可用；Q4 决定写入策略，发布时仍核对 SQL 原文/配置版本与 manifest |
| F5 | 中 | 前端 embedding 切换仍按同步重建结果提示成功；任务跨刷新恢复和 generation 状态缺少合同 | E5-07 调整现有 API/UI；见 KnowledgeBase.tsx:228、types/api.ts:273 |
| F6 | 中 | 既有 offline benchmark 使用 scripted model，不能证明真实向量检索质量与恢复 | E5-08 使用真实 Chroma/embedding，并单独记录人工核定的检索样本 |
| F7 | 高 | 现有 head 是 owner/index 整体范围，但业务任务以 entity 为单位；仅重建单文档后切 head 会遗漏其余文档 | generation 必须表达完整 scope snapshot，不能以单条 job 结果冒充完整索引 |
| F8 | 中 | BM25/检索异常可能变成空列表，HyDE 失败回原 query，笔记异常被省略；空结果无法证明投影健康 | E5-03/06 区分零命中、显式 fallback 和依赖故障，各分支独立负向测试 |

### 3.1 代码定位与可复用基础

| 位置 | 已有事实 | E5 差额 |
|---|---|---|
| [projection_domain.py](../../backend/app/models/projection_domain.py) 第 25/60 行 | 已有 rag_generations/rag_generation_heads；head 唯一键是 owner_scope_type/owner_scope_id/index_kind | 扩展现有结构，不另建竞争指针；source_revision 字段存在不等于发布时检查新鲜度 |
| [e2/rag.py](../../backend/app/e2/rag.py) 第 194 行 | SQL head 锁、revision、ready 和 scope 检查；旧 generation 标 retired | source/config manifest、当前 job fence、Chroma locator 与回收动作未形成端到端合同 |
| [jobs/repository.py](../../backend/app/jobs/repository.py) 第 513 行；[jobs/runner.py](../../backend/app/jobs/runner.py) 第 457 行 | SQL succeed fenced，lease loss 取消 handler | 不能撤销已开始的外部写入；需要 attempt 隔离与受保护发布 |
| [business_handlers.py](../../backend/app/jobs/business_handlers.py) 第 35 行 | 注入 projector(session, job_type, payload)，没有传入 context；E4 未注册真实投影 consumer | 传递必要 job/fence/cancel 上下文，显式兼容旧 payload，完成后才注册 |
| [vector_store.py](../../backend/app/rag/vector_store.py) 第 383/419 行 | 用户 collection 无 generation；add_documents 由 to_thread 执行 | 用 SQL active locator 选 collection，写 staging attempt，禁用原地 reset 接管新生命周期 |
| [knowledge_service.py](../../backend/app/router/knowledge_service.py) 第 340/357 行；[knowledge_document_service.py](../../backend/app/services/knowledge_document_service.py) 第 108/168 行 | 逐源重建、先写 Chroma 再标 indexed、原文物理删除 | 完整 scope snapshot 与内容版本校验；删除期间查询候选回 SQL 核验 |
| [rag_service.py](../../backend/app/rag/rag_service.py) 第 123/183/218 行；[hybrid_retriever.py](../../backend/app/rag/retrievers/hybrid_retriever.py) 第 29 行 | HyDE fallback、笔记省略、检索 broad catch 返回空；BM25 使用 Chroma 内容 | port、统一降级与 source/version 过滤必须覆盖每个分支 |
| [KnowledgeBase.tsx](../../front/src/pages/KnowledgeBase.tsx) 第 228 行；[api.ts](../../front/src/types/api.ts) 第 273 行 | embedding switch 仍读取同步重建统计并提示成功 | 对齐异步 job 和 active/desired 配置状态 |
| [test_e2_primitives.py](../../backend/tests/test_e2_primitives.py) 第 156 行；[test_job_runner.py](../../backend/tests/test_job_runner.py) 第 218 行 | generation 与 coroutine lease-loss 的合成测试 | 补真实在途 Chroma 写入、构建中源变更及重启清理测试 |

准备状态：执行批次已完成；Q1-Q7 已确认。实际结果、偏差和未完成验收项见 [execution-record.md](./execution-record.md)。

## 4. Grilling 决策树

已固定的根节点：单机单 MySQL、SQL 唯一业务权威、Chroma 可重建、runner 并发 1、知识与笔记纳入 E5、E4 已关闭、中间材料保留。

第一轮已确认（2026-09-10，用户原话：`q1按照建议 q2按照建议 q3 直接执行全量迁移不考虑旧访问性`）：

| 问题 | 确认结果 | 状态 | 解锁的后续设计 |
|---|---|---|---|
| Q1 generation 的用户边界 | 每用户、每 index_kind 独立生命周期，不跨用户共享 collection；generation 使用 UUID，metadata 强制 user_id | 已确认：按建议 | 复用 owner/index head 唯一键与独立回收范围 |
| Q2 配置变更的重建条件 | 解析/切片/embedding 触发重建；top-k/查询 filter/HyDE/rerank 更新 SQL 查询配置版本 | 已确认：按建议 | 索引/查询配置版本分离；查询缓存依新版本失效 |
| Q3 首次迁移的查询行为 | 从 SQL 全量重建，迁移期间停用旧 RAG；相关查询返回结构化 degraded/503，校验完成后开放新索引 | 已确认：用户选择全量迁移、不考虑旧访问性 | 无旧 RAG 连续服务或自动回退要求；失败保持不可用并修复/重试 |

第二轮前沿：

| 问题 | 建议 | 状态 | 依赖与影响 |
|---|---|---|---|
| Q4 首次全量迁移期间的写入 | 只在 E5 应用层暂停当前用户的知识原文、笔记和索引配置写入；不执行 MySQL 全局只读、全库锁或主机级停写。其他服务（包括 new-api）继续运行；同表外部写入由 corpus revision 检测并使 generation 失效后重建 | 已确认：按建议，但受主机边界修正 | 保护范围限于 E5 target 用户/index_kind；不改变数据库全局状态、不影响其他服务 |
| Q5 开放粒度 | 同一用户知识和笔记全部构建通过后一起开放 RAG；两类 generation 仍独立 | 已确认：按建议 | 用户级成组开放；任一索引未就绪则该用户 RAG 503 |
| Q6 文档失败处置 | 任一纳入范围的文档解析/embedding 失败则阻断该用户激活；已批准 excluded 项继续排除 | 已确认：按建议 | 失败记录、重试；禁止部分索引伪装为完整成功 |
| Q7 日常索引重建可用性 | 后续切片/embedding 重建也采用期间 503、成功后恢复；仅查询配置即时生效 | 已确认：按建议 | 统一停用/恢复合同；查询配置变化不触发重建 |

模型缓存与 E4 模型证据继续只读核验；核验结果将用于提出真实 embedding/reranker 验收参数，不要求用户提供可自行查得的事实。后续分支只围绕实际未决项展开，不重复 Q1-Q3。分支收束后提交具体执行清单，实施结束提交一次关闭验收；批次检查点不新增人工确认。

## 5. 拟定实施合同

Q1-Q7 对应规则已确认；首次全量迁移覆盖各 canonical 用户当前 SQL 中全部未排除的知识原文和笔记，旧 Chroma 的完整性或可用性不作为输入前提。E5 consumer 仅在 E5-01 的资源、备份、停写和恢复 gate 通过后启用。

1. **配置和向量空间**：SQL 分开保存索引与查询配置的 revision/digest。每用户/index_kind 独立 generation 和 collection，user_id 校验不可省略。解析、切片、embedding 变化触发重建；top-k、查询过滤、HyDE、rerank 变化只更新查询版本与相关缓存，不触发重新 embedding。影响入库内容或切片集合的过滤属于索引配置。embedding fingerprint 至少覆盖实际 provider/model revision、dimension、归一化及相关预处理；模型别名、可变目录名或 base URL 不能单独充当内容指纹。凭据不写入公开 manifest。
2. **可重建输入**：以 canonical SQL owner/source ID、原始 bytes/text、metadata、revision/content digest 和配置快照形成 manifest。chunk ID 可确定性重算；解析/切片版本和计数可对账。损坏/缺失原文不能以旧 Chroma 的内容补齐并伪装成功。
3. **RAG port**：core 不导入 Chroma；统一返回 `documents`、`scores`、`source_ids`、`generation`、`status`、`degraded_reason`。首次全量迁移先关闭相关 RAG 访问，返回明确的迁移中 degraded/503；禁止旁路使用旧 Chroma/旧 retriever cache。开始迁移时处理在途请求，重新开放后只使用新 active。明确空库正常结果与依赖故障的区别，说明 distance/similarity/rerank 分数的方向和融合方法。user_id 从认证上下文取得，不信任客户端过滤条件。
4. **异步重建**：复用 SQL job 和单并发 runner。写入 SQL 原文、配置及 enqueue 的事务不能拆开。长时间 parse/embed/index 必须允许 heartbeat 与核心 API 继续运行；查询请求只登记去重后的重建需求，不同步重建。
5. **过期任务**：SQL 完成时检查 fencing 不足以撤销已经发生的 Chroma 写入。写任务必须绑定 generation UUID 与独立 attempt/fence 的未激活构建产物；重试不共享废弃 attempt 的可写 namespace。过期 attempt 不得覆盖 active、激活旧 snapshot 或删除其他 attempt/generation。激活前再次检查 lease/fencing、owner、source/config revision 和 manifest。废弃构建产物隔离后回收，不作为可查询历史 generation；验证物理残留的有界处置规则。
6. **发布和失败窗口**：只有完整 scope staging 的数量/digest/向量维度与 SQL snapshot 对账通过，才在当前 job fence 保护的同一 SQL 事务内切 active 指针、记任务成功、写审计和登记回收需求。Chroma 写成功/SQL 失败、SQL 激活成功/回收失败、进程在各边界退出都必须可恢复。
7. **并发业务变更**：首次全量迁移和后续索引重建只暂停 E5 应用层内当前用户的知识原文、笔记、索引配置及会改变其内容的后台任务；不得设置 MySQL 全局 `read_only`、锁全库、停止主机服务或改变 new-api 的连接/权限。其他服务对同一源的写入由 corpus revision 与 immutable manifest 检测；发布前不一致则废弃/重排 generation，继续 503。generation 表示 owner/index 完整 snapshot，单 entity job 不能仅用该 entity 替换整个 head。查询配置不改变 corpus，可即时更新。任一时刻跨用户泄露和已删除内容返回必须为零。

   Q4 已确认采用 E5 应用层的范围停写：必须覆盖当前应用 API 与后台变更入口。现有 `business_handlers.py` 第 153 行默认注册 `e4.note.enrich`，会写回笔记标签/分类；只暂停页面编辑不足以固定本应用视角的 snapshot。应暂停本应用相关写任务并完成在途任务收束后抓取 snapshot，保留其他核心能力和主机服务。不得用数据库全局只读代替范围 gate；外部服务写入通过 revision mismatch 让 generation 失败并重排。
8. **清理**：active + staging 是正常运行状态，不增加历史 generation 功能。成功切换后立即安排幂等回收；处理在途读取、失败重试和 restart 对账，未清理完成不能计作清理验收通过。SQL manifest/审计可以保留。旧输入、故障证据、E1-E4 材料和健康恢复快照不在运行期回收范围。
9. **故障和降级**：初始化、collection 丢失、损坏、权限、版本、embedding 不可用、重建失败使用稳定错误码。RAG 无可用健康索引时返回结构化 degraded/503；HyDE/BM25/笔记/rerank 不能吞掉必需依赖错误并伪装为完整成功。核心登录、会话和原文写入不因 Chroma 故障失效。
10. **既有调用方**：配置变更和上传的 accepted/job 状态与索引 ready 分开；以 SQL job/generation 查询恢复页面状态，更新必要 OpenAPI/TypeScript/SSE 合同。E5 验证向量、HyDE、BM25、笔记、rerank 的实际链路；E7 仍承担更广泛的业务回接和遗留清理。

## 6. 执行顺序与完成判据

| 批次 | 内容与预期文件范围 | 完成判据 |
|---|---|---|
| E5-01 | 资源、队列、原文和配置只读 inventory；E5 ops/preflight 与备份/恢复参数 | target 身份、精确 schema、Chroma 隔离路径、模型版本、输入 manifest、恢复点齐备；旧资料不变 |
| E5-02 | SQL generation/config/manifest 的 additive schema 与索引约束；复用现有 UoW/job | 空库和 populated restore migration 通过；稳定 UUID/FK、唯一 active、配置/源版本检查可验证 |
| E5-03 | RAG port、Chroma adapter、分数及错误合同、认证 owner 过滤 | 同一合同覆盖真实 adapter 与测试替身；无客户端 user_id 绕过或底层异常伪成功 |
| E5-04 | SQL 全量原文 parse/split/embed/index handler；E4 queued job 兼容；受控启用 consumer | 覆盖全部未排除源；可幂等重放、暂停/取消/retry/DLQ；过期 attempt 不修改 active；长任务不阻塞 heartbeat |
| E5-05 | 首次迁移 RAG 访问门、staging 校验、SQL active 切换、回收与启动 reconciliation | 迁移期间 503、旧查询无旁路；按 Q5/Q6 条件开放新索引；source/config 漂移、崩溃和清理失败可恢复 |
| E5-06 | 向量、HyDE、BM25、笔记、rerank 使用统一 port 与版本上下文 | canonical source ID 可追溯；空结果/降级可区分；SQL 删除和跨用户阻断覆盖全部路径 |
| E5-07 | 现有 knowledge/config/job API、前端知识页和必要 SSE 类型 | 保存/排队/构建/激活/失败状态准确，刷新和重启后恢复；配置在约定时机生效 |
| E5-08 | 真实 MySQL + 独立 Chroma + 实际 embedding/reranker，故障及 SQL 恢复重建 | 证据矩阵全部通过；真实结果和 fixture 限制分别记录；E4 核心回归不退化 |
| E5-09 | 实施日志、对账、故障与回滚报告、主文档更新 | 先提交待验证；用户明确关闭后才进入 E6 |

每批开始前关联代码文件、预期 schema/配置变更、证据 ID、影响和回滚点。未准备的脚本或命令必须先实现并在隔离环境验证，不能把拟定命令当成可执行交付。

## 7. 执行环境与恢复准备

实施前按顺序完成：

1. 固定当时的 commit、dirty diff、解释器/锁文件版本；核验 E4 关闭证据和已有材料摘要。
2. 从 E4 已记录资源定位 canonical target 和独立 restore 目标，记录用途、server UUID、database、账号权限与 schema。E5 单独生成自己的资源清单和短时 preflight；不照搬 E4 token，不假设容器还在运行。
3. 为 E5 创建独立、明确路径的 Chroma 工作区；核验与旧 Chroma、受保护材料无父子/别名重叠。只从 SQL 重建，旧 collection 名不成为 canonical owner 映射依据。
4. 在变更前备份 SQL 和配置，记录 manifest/digest；在独立 restore 目标验证恢复与 additive migration。故障注入只针对 E5 测试副本。
5. 只读统计当前源/配置和 queued job；检查早期 E4 job 的 payload、对象删除和 revision 漂移，确定显式兼容/重放方案后才启用消费。
6. 正式模型基线记录实际 embedding/reranker 的版本、维度、指纹、输入限制及失败码。基础镜像、数据库或模型不可用时记录实际阻断，不以默认下载、mock 或别的账号数据补齐。

失败恢复顺序：暂停 E5 消费和索引切换，保留 job/attempt/active pointer/manifest/审计；首次迁移或日常索引重建失败期间相关 RAG 继续 degraded/503；复验 SQL 与 Chroma 身份，修复失败原因后从 SQL 全量重建新 generation，不自动恢复旧 RAG 访问。SQL 本身需恢复时，用已验证 dump 在独立目标执行 restore-forward 并对账，不在 populated 业务库直接 downgrade。恢复后先验证身份/FK/digest/权限与源版本，再按 Q5/Q6 的完整性条件开放新 RAG。SQL 恢复材料和受保护输入继续保留。

不得直接切回 E4 已冻结的 source，它没有 target 切流后新增事实。E4 部分运行入口位于 Git 忽略的 `.runtime/e4/`；E5 必须把所需的可复现入口和参数规范放到受版本控制的位置，秘密与实际备份仍留私有目录。

### 7.1 已核实工具与启动前检查

| 项目 | 本轮只读观察 | 使用约束 |
|---|---|---|
| Python / uv | 仓库 venv Python 3.12.3；uv 0.8.17 | 测试显式使用 backend/.venv/Scripts/python.exe；裸 pytest 指向 Anaconda |
| Chroma | chromadb 1.5.9、langchain-chroma 1.1.0；lock 与已安装元数据一致 | 尚未验证 native runtime 或真实 collection |
| 模型栈 | sentence-transformers 5.5.1、transformers 5.12.1、torch 2.12.0+cu132 | 未证明 CUDA、模型缓存、维度、指纹或推理可用 |
| 检查工具 | pytest 9.1.0、Ruff 0.15.17；Node 22.20.0 和 npm.cmd 位于 C:/nvm4w/nodejs | Node 不在当前 PATH；mysql/mysqldump/pwsh 未在 PATH 找到，执行时明确二进制或容器来源 |
| 运行状态 | E4 target/restore/Redis 为 Exited (255)；33427/33428/18020/18000/18001/18080/11434 无监听；3306 有监听 | 仅表示观测时状态，不证明 source 权限、freeze、schema 或业务可读性 |

本轮准备可重复执行的无业务副作用命令，工作目录为仓库根目录：

```powershell
git --no-optional-locks status --short
git log -5 --format='%h %ad %s' --date=short
& .\backend\.venv\Scripts\python.exe -I -S --version
uv --version
& 'C:/nvm4w/nodejs/node.exe' --version
& ./scripts/check-docs.ps1
git diff --check
```

实施后的测试命令使用独立终端和仓库隔离配置，下面是既有入口，不代表本轮已运行：

```powershell
# 工作目录：backend；新增 E5 测试随对应实现纳入。
& .\.venv\Scripts\python.exe -m pytest tests/test_e2_primitives.py tests/test_job_runner.py -q
& .\.venv\Scripts\python.exe -m pytest tests -q
& .\.venv\Scripts\python.exe -m ruff check app tests scripts
```

前端从 `front` 目录使用包含 Node 的 PATH 执行 `npm.cmd test` 与 `npm.cmd run build`。现有 [CI](../../.github/workflows/ci.yml) 和 [conftest.py](../../backend/conftest.py) 是锁文件/测试隔离依据。新增 RAG 相关测试必须补入实际验证清单，不能用上述两个基础测试替代 E5 集成证据。

已有运维入口的复用边界：`e4_preflight.py` 会连接数据库并写证据；`e4_inventory.py` 会打开 Chroma SQLite；`e4_import.py --preflight` 不是只读模式；`e4_runtime.py` 启动后可能消费 SQL job；`backup_restore.py rebuild_projection` 是文件 bundle 的 staging/rename，不是 SQL 原文重新 embedding，且 SQL 子命令使用 E2 guard。本轮没有运行这些入口；E5 应复用已审查的机制并建立自身参数/guard，不能只改 DSN 后直接调用旧阶段脚本。

## 8. 验收门槛

- [ ] canonical 原文、配置、job、generation 和 audit 全部可由 SQL 追溯；不写向量 BLOB。
- [ ] source/chunk manifest、数量、digest、embedding dimension/fingerprint 对账通过；无未解释差异。
- [ ] 跨用户、已删除/不可授权 source、过期 attempt 的激活或清理成功次数为零。
- [ ] 重复/乱序、取消、租约过期、kill/restart、长任务 heartbeat、SQL/Chroma 分裂提交全部通过。
- [ ] 正常向量、HyDE、BM25、笔记与 rerank、用户声明式配置和当前生效版本通过真实 E2E。
- [ ] 首次全量迁移覆盖所有纳入范围的 SQL 原文/笔记；迁移与失败重试期间 RAG 503，无旧 Chroma 或 retriever cache 访问旁路；新索引验收通过才重新开放。
- [ ] 每用户/index_kind 独立 generation；仅查询参数变化不提交索引重建任务；索引配置变化能生成新的 staging 和可追溯 manifest。
- [ ] 损坏/权限/版本不兼容/collection 缺失/进程重启故障均有真实证据；RAG 503，核心认证/会话可用。
- [ ] 从 SQL 原文和配置在全新 Chroma 工作区恢复成功；不依赖旧向量或 sidecar。
- [ ] 成功切换后的运行期旧 generation 已回收，清理失败可重试且不损坏新 active；受保护输入摘要不变。
- [ ] 前端不把 accepted/queued 当作 indexed；刷新后状态可恢复，错误和进度与 SQL 一致。
- [ ] 检索质量样本及阈值在实际测试前冻结；报告命中、漏检、隔离负例、延迟和重建时间，不用 offline 路由分数代替检索质量。
- [ ] 后端相关测试/完整回归、Ruff、前端测试/build、文档和 diff 门禁通过；单平台、真实模型和替身边界写清。
- [ ] 用户审阅证据并明确批准关闭 E5。

## 9. 当前未完成

- Q1-Q7 已全部按建议确认；Q4 按主机边界修正为 E5 应用层范围 gate，不使用全局 SQL 只读。Q5 要求知识和笔记全部成功后一起开放，Q6 要求任一纳入范围文档失败即阻断，Q7 要求日常索引重建期间同样返回 503。
- 本轮已完成 SQL additive migration、独立恢复演练、真实 Ollama embedding、隔离 Chroma consumer、运行期回收和必要 API/UI 修正。
- 真实 reranker、HyDE 和 BM25 分支已补充 live 证据；关闭前保留用户审阅门槛。
- 准备阶段检查和历史证据见 [test-record.md](./test-record.md)，文档变更见 [change-log.md](./change-log.md)。
