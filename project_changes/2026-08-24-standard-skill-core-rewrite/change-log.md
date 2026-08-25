# 标准 Skill 核心重构变更记录

日期：2026-08-24

状态：A 级和有限 B 级开发支持已形成；C 级未实现；门禁未通过

## Package 与 Storage

- 新增标准 `SKILL.md` package parser，解析 frontmatter、指令和资源 manifest，并保留未知 frontmatter 字段。
- ZIP/目录统一拒绝路径穿越、绝对/盘符路径、symlink/junction/hardlink、特殊文件、大小写/Unicode 名称碰撞、超限体积、压缩比和 ZIP 炸弹。
- package 以 digest 为键写入仓库外 content-addressed immutable Storage，写入经过 checksum 校验和原子 finalize，不污染 Git 工作树。
- 标准 seed package 保留在 `backend/app/skills/seed_packages`，启动时通过同一 validator/Storage/Registry 链幂等安装。

## 领域、生命周期与 API

- 新增 Skill、Alias、Version、Installation、Import、AuditEvent、CapabilityGrant、SkillRunBinding、RegistryState 和 RegistryEvent 领域模型及 Alembic revision `20260824_0002`。
- 生命周期覆盖 draft、ZIP import、approve、publish、settings、activate/rollback、archive、export 和资源读取。
- import 记录固定 `target_revision`，审批/发布对目标 revision 执行并发保护。
- 管理员 catalog 合并数据库纯 draft，因此新建但尚无 active version 的 Skill 可管理；普通 catalog 和运行 Registry 只暴露已发布、可见、已授权内容。
- Skill 路由和 response schema 已同步到静态 OpenAPI。

## 授权、RunBinding 与一致性

- CapabilityGrant 持久化批准的 Tool/能力边界；显式 `skill_ids`/`tool_ids` 仍须经过 visibility、scope、grant 和 Tool policy 的交集。
- private Skill/Tool 不再因知道 ID 而可被普通用户选择，versions/export/resources 复用同一可见性边界。
- 每轮 SkillRunBinding 固定 version ID、digest、Registry revision 和 effective grants；高风险确认继续绑定同一运行快照，避免状态变化后的 TOCTOU。
- B 级资源读取与普通 Tool 使用统一调用次数预算，资源工具固定到本轮不可变 package 版本。
- Registry revision/outbox reconcile 支持多实例收敛、目标 revision 对账和旧事件恢复；无法达到目标 revision 时统一抛出 `SkillRegistryStaleError`，HTTP 返回 `503`，不静默使用陈旧快照。
- 同一 Session 的版本切换和 relationship 刷新已纳入事务一致性测试。

## 管理前端

- Skill 管理页覆盖新建、ZIP 导入、审批、内容编辑、设置、版本历史、激活/回滚、导出和归档。
- 资源支持上传、替换、删除和撤销；保存通过增量 `resource_changes` 修改 package，不会因只编辑正文而清空未修改资源。
- 导入轮询兼容审批和发布终态，canonical Skill name 创建后不可修改。
- 管理员可见纯 draft；普通用户不获得管理动作或未发布内容。
- 对 `format_compatible=true` 但 `runtime_ready=false` 的 C 包，前端允许以 `enabled=false`、`default=false` 批准并禁用安装，同时明确禁止启用或执行。

## 旧运行时退出

- 删除 `backend/app/agent/skills` 下 20 个旧 `SKILL.md`/`skill.yaml` 运行文件。
- 新增静态禁回归测试，禁止重新引入旧 `skill.yaml` loader、源码目录写入、旧运行目录引用或双 Registry。
- 旧目录不再承担 seed；标准 seed package 是唯一受支持的内置内容来源。

## 合同、文档与产物

- 更新主 README、文档索引、当前架构、Agent runtime、架构计划、执行计划、路线图和标准 Skill 规格。
- 更新 `backend/openapi.json`，OpenAPI 漂移检查通过。
- 更新同主题 plan、change log 和 test record；工作包 `7-10` 保留并冻结。
- `scripts/check-docs.ps1` 忽略 Git 索引中存在但工作树已经删除的 cached 路径，避免把已退出旧 Skill 文件计入文档扫描。
- Benchmark results、前端 `dist` 和其他中间产物受 ignore 规则保护，没有进入 Git 跟踪清单。

## 保留边界

- import/validation/publish 仍在 API 路径完成，不是具备 lease/retry/cancel/DLQ 的 durable worker。
- 当前安装范围仍是 system/global，per-user scope 未实现。
- B 资源已有统一调用次数预算，但没有跨多次读取的累计 token 预算。
- 尚缺真实 MySQL/startup/API lifecycle 和任意第三方 A/B package 聊天 E2E。
- 含 `scripts/` 的格式兼容包可以禁用安装和管理，但必须保持 `runtime_ready=false`，不得启用或执行；C 级 Node/Python runner、依赖构建、沙箱和进程树终止未实现。

这些项目均是 `SKILL-GATE` 阻断项；`SKILL-GATE`、`ARCH-GATE` 均未通过，不能声明通用可执行 Skill 已完成。
