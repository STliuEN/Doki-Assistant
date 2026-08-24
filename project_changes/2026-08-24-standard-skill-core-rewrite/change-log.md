# 标准 Skill 核心重构需求文档变更记录

日期：2026-08-24

状态：完成（仅需求与计划文档）

## 已确认架构决策

- 弃用当前 `skill.yaml + SKILL.md + 源码目录 Registry` 内置 Skill 能力。
- 所有来源统一为标准 `SKILL.md` package，不保留长期双 Registry 或前端私有格式。
- 前端继续提供可视化管理，但保存、版本和导出都使用标准兼容 package。
- 现有 Skill 经一次性 migrator 转换；观察期后删除 loader、文件 CRUD、进程内 reload 和硬编码业务路由。
- 标准 Skill 设为工作包 `11`，按 `SK-0` 至 `SK-5` 当前优先执行；`SKILL-GATE` 是 `ARCH-GATE` 的前置组成条件。
- package 使用统一 MySQL + canonical Storage，不增加第四种数据库；脚本只进入隔离 worker。

## 活文档变更

- 新增 `docs/standard_skill_integration_requirements.md`：标准 package、兼容等级、领域模型、可视化管理、授权、生命周期、API、迁移、实施序列和验收矩阵。
- 更新 `docs/architecture_rewrite_plan.md`：加入 `SK-0` 至 `SK-5`、`SKILL-GATE`，并把 Skill 调整为 Storage/worker/后端/前端首个业务落点。
- 更新 `docs/roadmap_next.md` 和 `docs/improvement_execution_plan.md`：工作包 `11` 改为当前核心必做，工作包 `7-10` 保留并继续冻结。
- 更新 `docs/security_hardening_plan.md`：新增 `SKILL-01 P0`。
- 更新 `README.md`、`docs/README.md`、`docs/project_develop.md`、`docs/development_setup.md` 和 `docs/agent_runtime_improvements.md`：同步当前能力、目标入口和过渡说明。
- 更新 `project_changes/README.md` 并建立本目录三件套。

## 未执行

- 未修改任何 Python、TypeScript、schema、migration、依赖或部署配置。
- 未运行 Skill 导入、迁移、脚本或服务。
- 未连接或修改现有 MySQL、Redis、Chroma 或用户文件。
- 未删除当前 Skill 目录或旧实现。
- 未声称任何 `SK-*` 或架构门禁已经完成。

## 下一实施项

与 AR-0 同步执行 `SK-0`：格式 ADR、威胁模型、兼容矩阵、资源上限、旧目录 checksum inventory、API/UI/Prompt/路由 characterization 和恶意 package fixtures。
