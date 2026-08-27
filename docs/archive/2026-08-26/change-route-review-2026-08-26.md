# 改动路线审阅报告（多模型平行审阅 + 交叉审阅 + 组织者复核）

> 日期：2026-08-26
> 状态：**审阅记录，供交接执行**。本报告不改变 `architecture_rewrite_plan.md` 的事实源地位；执行改动前请以该文档为准，并把本报告结论以批次方式落入 `project_changes/`。
> 审阅对象：`docs/` 活计划体系（架构重写计划 / 产品路线图 / Skill 规格 / 安全基线 / benchmark / agent 运行时 / MCP / 开发说明）+ 项目实际（代码 / 测试 / git 状态 / 历史批次证据），分支 `ai_document_assistant`。
> 审阅方法：4 位模型各自独立审阅**同一份完整材料包**（66KB：活计划全文/摘录 + 历史批次证据 + 组织者代码事实清单 F1-F10），随后各自交叉审阅全部报告，最后 gpt-5.6-sol 第二实例做独立复核收口。

## 0. 审阅参与情况

| 角色 | 模型 | 独立审阅 | 交叉审阅 | 说明 |
|------|------|:--:|:--:|------|
| 审阅员 A | gpt-5.6-sol | ✅ 10 条发现 | ✅ | 覆盖面最广，侧重门禁可执行性 |
| 审阅员 B | kimi-k3 | ✅ 10 条发现 | ✅ | 侧重计划-现实对齐与结构性风险 |
| 审阅员 C | glm-5.3 | ✅ 7 条发现 | ✅ | 侧重证据链与内部矛盾 |
| 审阅员 D | claude-fable-5 | ❌ | ❌ | 网关渠道持续故障（upstream error），未能参与 |
| 复核员 | gpt-5.6-sol（第二实例） | — | — | 确认 6 项共识、仲裁 4 项分歧、补漏 6 项 |
| 组织者 | DeepSeek 娘 | ✅ 8 条发现 | — | 独立验证事实锚点 F1-F10 |

## 1. 执行摘要（总体结论）

1. **路线骨架成立**：AR-0→AR-1→AR-2/3→AR-4/5→SK-5 依赖链未发现循环；四门禁（SKILL-GATE / ARCH-GATE / EXEC-SKILL-GATE / PUBLIC-HA-GATE）能力边界互不冒充；"当前停留 AR-0 + SK-0、所有退出门未通过"的判定经代码级独立验证**属实**。
2. **文档诚实度高**：08-25 校准批次主动撤回无法证明的完成声明（"前端未复跑""Windows-only lock 不能证明跨平台""seed 不能替代通用迁移器"等），多份验证记录确认未连接/修改现有 MySQL——这种审计透明度高于常见项目。
3. **但存在两类必须立即处理的裂缝**：
   - **审计链裂缝（P0 级）**：工作树约 123 个未提交文件（+22084/−38229 行，含 34 py / 28 tsx / 18 ts 业务改动）与校准批次"仅修改 Markdown、未修改业务实现"的声明无法从时间戳对账；08-25 批次 change-log"待最终差异审查后填写"与 test-record"最终检查待填"留空。唯一事实源所描述的"当前现实"基线因此不可审计。
   - **门禁证据规格缺口（P1 级）**：SKILL-GATE 的"真实依赖故障/恢复抽样通过""完整审计""多实例可靠收敛"等条件没有规定测试命令、环境拓扑、样本集、阈值、证据文件格式与批准人；本地单实例档位与"多实例收敛"要求存在验证能力不匹配。
4. **两个代码级 P0 经独立验证属实**（与文档声明一致）：Chroma 初始化失败路径 `shutil.rmtree` 递归删除持久目录（`backend/app/rag/vector_store.py:39-43,109`）；Skill import/publish 在 API 请求内同步执行、发布为 best-effort 进程内操作（`backend/app/skills/service.py:346,584`），无 durable worker、无 lease/fencing。

## 2. 高可信共识发现（≥2 位审阅员独立指出且交叉审阅确认）

### P0 阻断

| # | 发现 | 证据 | 建议动作 |
|---|------|------|----------|
| C1 | **Chroma 破坏性 reset**：初始化失败路径递归删除持久目录，违反"Chroma 不删除持久目录"前提；216 passed 离线测试不能证明真实故障安全 | `vector_store.py:39-43,109`；架构计划 §3.2/§4 AR-0；08-25 change-log | 移除生产路径递归删除，改为失败隔离 + 显式 quarantine；以临时损坏/权限错误/版本不兼容/部分 collection 缺失/重启恢复为维度做故障注入，证明原目录不变、readiness 分层正确、projection 可重建；证据列入 AR-0 最低集 |
| C2 | **Skill import/publish 非持久、非原子**：请求内同步执行，发布为事务提交后 best-effort 进程内操作；无 durable job/lease/fencing/重试；激活前无 Storage digest 重验 | `skills/service.py:346,584`；架构计划 §2.1/§3.2；08-24 change-log"保留边界" | AR-0 先止血：服务端固定 `installed_disabled`、失败路径 fail-closed 或限受控诊断模式；再按 AR-1 交付 durable job + UoW/outbox + lease + 幂等键 + DLQ + 重启恢复，以 Skill import 为真实 worker consumer 做 kill/restart、重复、乱序测试 |
| C3 | **工作树基线不可审计**：123 个未提交业务文件与"仅修改 Markdown"声明矛盾；08-25 批次记录留空；08-25 08:49 业务提交无对应 project_changes 批次 | 事实 F6/F8；08-25 plan"非目标"/change-log"待最终差异审查后填写" | 固定审阅基线与变更集合：记录 commit、工作树状态、纳入/排除路径、每批 scoped diff 与 hash；补完 test-record 最终命令与结果；未复跑项（前端/真实依赖）保持"未验证"标注，不得进入完成摘要 |

### P1 重要

| # | 发现 | 证据 | 建议动作 |
|---|------|------|----------|
| C4 | **MCP / Tool policy 仍是本地 YAML 权威**：`config.py:25` copyfile 初始化本地配置，策略变更只影响单进程、无 Registry revision，RunBinding 无法固定 digest；与权威矩阵"本地 YAML 不得是最终权威"冲突，且 MCP 计划未标注收敛阶段 | 事实 F7；架构计划 §2.2；MCP 集成计划"当前实现" | AR-0/SK-0 冻结 YAML 写入边界，明确其仅为 adapter/cache；设计 Tool/MCP 版本化 MySQL schema + digest + 迁移 inventory + RunBinding 绑定 + 回滚证据；"旧 YAML 不再是最终权威"列为 SKILL-GATE 可执行检查项（归属 AR-3/AR-5） |
| C5 | **门禁退出条件不可判定**：缺命令、环境拓扑、样本集、阈值、证据格式、批准人；现有证据主要为 unit / offline SQL / FakeAgent / 静态检查 | 架构计划 §3.2/§5.1；SKILL-GATE 条件；08-24 test-record | 为每个门禁条目建立可机器检查的证据模板（环境/平台/版本/fixture/命令/预期/实际/阈值/失败处理/日志/负责人）；真实依赖故障注入、恢复、多实例测试变成有编号的 exit evidence |
| C6 | **R7 前置与当前环境死锁风险**：队列第 1 条"建立 R7 最小测试入口"包含前端复跑与真实依赖，但当前 shell 无 Node/npm、真实基线未建立 | 架构计划 §3.3 第1条；roadmap R7 行 | 拆分 R7：证据模板、scoped diff check、后端失败回归立即执行；前端复跑与真实依赖基线作为环境恢复后的独立项（gpt 分身仲裁结论） |
| C7 | **SKILL-GATE 混入多实例要求**："多实例 consumer offset、乱序幂等、跨实例收敛"是部署拓扑能力，本地单实例档位无法提供真实证据，门禁不可达或只能用替身 | 架构计划 §5 SKILL-GATE；kimi F2 | SKILL-GATE 只保留单实例 worker 的 durable job / lease / fencing / 重启恢复 / 幂等语义；多实例收敛移入 PUBLIC-HA-GATE（gpt 分身仲裁结论） |
| C8 | **提前切片返工影响未评估**：AR-0 P0 止血（发布重验、installed_disabled、Registry 隔离）会触及已落地的 parser/Skill domain/revision-outbox 等提前切片 | 架构计划 §3.2 提前切片列 | AR-0 退出材料中逐项列出受影响模块、返工范围与重新验证项，防止"止血破坏已验收切片" |
| C9 | **备份/恢复工具链无归属**：计划多处要求"无备份不得迁移/删除数据"且 AR-0 最低证据含备份抽样，但无任何阶段交付备份工具本身（脚本/manifest/演练 runbook）——隐性循环依赖 | 架构计划 §3.3/§5.1；kimi F6；gpt 分身补漏 | 备份/恢复最小工具链（MySQL、Storage、Chroma projection）作为 AR-0 前置交付，含可重复的一次备份+恢复演练 |
| C10 | **08-24 test-record 内部矛盾**：声称"OpenAPI 与当前 Skill lifecycle/错误合同一致"，同批 plan 与安全计划却确认 409/413、ZIP media type、CORS 缺口为未关闭 SKILL-03 P0 | 08-24 test-record 末条 vs 08-24 plan 审阅结论 vs 安全计划 API-01 | 修订 test-record 措辞为"仅覆盖已实现子集"，消除证据污染（glm 独有发现，经复核确认属实） |

### P2 建议

| # | 发现 | 证据 | 建议动作 |
|---|------|------|----------|
| C11 | **Legacy 迁移输入时间敏感**：旧运行目录在 inventory/迁移器前已删除，Git 历史是唯一迁移输入，越久越劣化；只读 checksum inventory 尚未开始 | 事实 F3；Skill 规格"迁移证据必须从只读备份/Git 历史离线重建" | 尽快从最后包含旧目录的提交或只读备份导出文件清单与 digest，不能未核对就断言 Git 历史是唯一输入 |
| C12 | **授权与审计无统一合同**：仅单一 admin、settings 可能覆盖 grant；actor/scope/digest/revision/grant diff/理由/有效期/结果/correlation ID 分散多阶段；负向测试缺失 | Skill 规格 §4.2/§14-15；安全计划 SKILL-01/03 | 发布不可绕过的授权审计合同 + 角色分离（内容管理员/安全管理员）+ approve/revoke + 撤销传播 fail-closed + 越权/重放负向测试 + API/worker/恢复对账 |
| C13 | **前端验证基线时效性**：安全计划基线表"2026-08-24 最终复跑"易被误读为当前状态；dist 产物晚于前端相关提交且含未提交改动 | 事实 F9；安全计划"已验证基线"表 | 基线表前端条目加注"结果来自 08-24 环境，当前工作树未经复跑验证" |
| C14 | **横切运营能力无 owner**：数据保留/删除、密钥轮换、N/N-1 兼容窗口、容量压测、供应链响应、备份加密、告警值班、恢复权限未形成阶段输入/负责人/退出证据 | 架构计划 AR-1~AR-6；gpt F10 | 为各项绑定 R7/R8 证据包与 owner，分别挂到 AR-2/AR-3/AR-4/AR-6 入口或退出条件 |

## 3. 分歧点与仲裁结论

| 分歧 | 各方立场 | 仲裁（gpt 分身 + 组织者） |
|------|----------|--------------------------|
| 123 个未提交文件的严重级别 | kimi 定 P0；gpt/glm 定 P1 | **暂按 P1 管理**，但盘点若证明改动属于待审代码或影响既有门禁结论则**升级 P0**。立即盘点优先于定级 |
| MCP YAML 权威问题的严重级别 | gpt 定 P0（F3）；kimi/glm 定 P1 | **P1**，AR-0/SK-0 冻结新增 YAML 写入与策略判定依赖，迁移阻断归 AR-3/AR-5 |
| SKILL-GATE 是否含多实例要求 | kimi 认为门禁定义错误；gpt 认为文字覆盖过全但不可判定 | **SKILL-GATE 只保留单实例 worker 能力**；多实例收敛移入 PUBLIC-HA-GATE |
| R7 是否阻塞 AR-0 | kimi 认为死锁；gpt 认为可拆分 | **拆分 R7**：当前环境可完成的（证据模板/scoped diff/后端失败回归）立即做；前端与真实依赖作为环境恢复后的独立项 |

## 4. 审阅质量评估与局限

- 三份独立报告 + 三份交叉审阅**未发现幻觉或虚构证据**：关键代码引用（`vector_store.py:39-43/:109`、`skills/service.py:346/:584`、`mcp/config.py:25`）与量化数据（123 文件、+22084/−38229、27 测试文件、216 passed）均可与项目实际核对。gpt 覆盖面最广、kimi 结构性最强、glm 证据链最细。
- 局限：claude-fable-5 因网关渠道故障缺席（应补一次独立审阅）；glm-5.3 为深度推理模型，输出受配额影响（已用 `reasoning_effort=low` 控制并复跑成功）；审阅基于工作树快照而非固定 commit，后续执行应以新固定基线为准。
- 结论的可信度分层：**C1/C2/C3/C4/C5** 为 3/3 共识 + 交叉确认 + 组织者代码验证，可信度最高；C10/C11 为 glm 独有但经复核确认属实；其余为 2/3 共识 + 仲裁。

## 5. 可执行改动清单（交接 IDE 小伙伴用）

> 约定：每个动作先建 `project_changes/<日期-主题>/plan.md`，完成后补 `change-log.md`、`test-record.md`；沿用"绿色测试/生成文件 current 不作为退出门"纪律。

### P0（阻断项，做完前不得进入 AR-1 / 解冻工作包 7-10）

| 动作 | 归属 | 验收方式 |
|------|------|----------|
| P0-1 移除 Chroma 生产路径破坏性 reset，改为失败隔离 + 显式 quarantine；不删除持久目录 | RAG/平台 | 临时损坏/权限错误/版本不兼容/部分 collection 缺失/重启恢复 5 类故障注入：原目录不变、readiness 分层正确、projection 可由 MySQL/Storage 重建；证据入 AR-0 最低集 |
| P0-2 Skill 发布链路止血：服务端固定 `installed_disabled`；import/publish/activate/rollback 在超时、重复、校验失败、digest 不匹配、中断时返回稳定合同错误；坏包不得发布 ready、ack outbox、清空 Registry 或同 revision degraded 运行 | Skill 平台 | 针对上述场景的 API 级负向测试 + 回归；409/413/ZIP media type/CORS/OpenAPI 合同修正并复跑漂移检查 |
| P0-3 固定工作树与变更批次基线：盘点 123 个未提交文件归属（08-24 重构未提交部分 vs 校准批次 vs 游离改动）；补完 08-25 批次 change-log/test-record 留空项；08-25 08:49 业务提交补批次记录 | 发布/审计 | 每个文件有批次归属或明确排除理由；文档声明可由提交历史 + hash 独立复核；前端未复跑项标注"未验证" |
| P0-4 冻结 MCP YAML 权威边界：明确本地 YAML 仅为 adapter/cache；新增策略写入与判定依赖 fail-closed | MCP/架构 | 文档与代码均能证明旧 YAML 不能作为最终权威；迁移合同入 AR-3/AR-5 阻断条件 |
| P0-5 建立 AR-0 可执行证据包：证据模板（环境/命令/阈值/责任人）、scoped diff check、后端失败回归在当前环境可运行；真实 MySQL/Redis/Storage/Chroma 隔离基线环境就绪 | 质量工程 | 证据模板样例 + 回归脚本可复跑；真实依赖拓扑（含 worker 独立启动、故障注入、恢复 runbook）文档化 |
| P0-6 交付最小备份/恢复工具链（MySQL、Storage、Chroma projection） | 平台/SRE | 对每个要求保护的对象完成一次可重复的备份 + 恢复演练并留证据 |

### P1（AR-0 期间并行推进）

| 动作 | 归属 | 验收方式 |
|------|------|----------|
| P1-1 按仲裁修订门禁定义：SKILL-GATE 只保留单实例 worker 能力，多实例收敛移入 PUBLIC-HA-GATE | 架构（文档） | 修订后两门禁条件与本地档位验证能力匹配，无替身证据要求 |
| P1-2 拆分 R7：证据模板/scoped diff/后端失败回归立即执行；前端复跑与真实依赖基线列为环境恢复后独立项 | 质量工程 | 当前环境可跑项有实际执行记录；不可跑项有明确环境依赖与恢复条件 |
| P1-3 发布授权与审计合同：角色分离、grant approve/revoke、撤销传播、审计事件全集 + correlation ID；负向测试 | 安全/身份 | approve/revoke/过期/拒绝/回滚/越权/重放测试通过；审计对账（API/worker/恢复）证据 |
| P1-4 保护 Legacy 迁移输入：从最后含旧目录的提交/只读备份导出 inventory + digest；修订 08-24 test-record OpenAPI 措辞；评估 P0 止血对提前切片（parser/domain/outbox）的返工影响矩阵 | 迁移/文档 | inventory 可复核；test-record 不再绝对化；AR-0 退出材料含切片影响矩阵 |

### P2（可排期）

| 动作 | 归属 | 验收方式 |
|------|------|----------|
| P2-1 横切运营能力绑定 owner：数据保留/删除、密钥轮换、N/N-1、容量预算、供应链、备份加密、告警、恢复权限 | 架构委员会 | 每项有交付物/命令/阈值/责任人/退出条件 |
| P2-2 安全计划基线表前端条目加注时效性说明 | 文档 | 基线表不再被误读为当前状态 |

## 6. 审阅产物（本报告依据）

- 独立审阅报告：gpt-5.6-sol（10 发现）/ kimi-k3（10 发现）/ glm-5.3（7 发现）
- 交叉审阅意见：gpt-5.6-sol / kimi-k3 / glm-5.3（各确认共识 5-6 项、分歧 3 项）
- gpt-5.6-sol 第二实例复核（确认 6 共识、仲裁 4 分歧、补漏 6 项、执行优先级 10 条）
- 组织者代码事实清单 F1-F10（Chroma reset / 同步 import / 旧目录删除 / 禁回归测试 / containment / 游离改动 / MCP YAML / 提交历史 / dist 时效 / 三进程拓扑）

*本报告由 DeepSeek 娘组织，gpt-5.6-sol / kimi-k3 / glm-5.3 平行审阅并交叉，gpt-5.6-sol 第二实例复核，2026-08-26。*
