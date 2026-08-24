# 标准 Skill 核心重构需求文档计划

日期：2026-08-24

状态：文档计划完成；实现尚未开始

## 背景

当前 Doki 使用私有 `skill.yaml + SKILL.md`、源码目录写入和进程内 Registry。审阅确认它不能直接接入只有标准 `SKILL.md` 的 package，也缺少资源、脚本、版本、授权、回滚和隔离执行能力。

需求经过两次确认后固定为：

- 不保留原有内置 Skill runtime。
- 全面采用标准兼容 Skill package 单轨管理。
- 前端提供统一可视化新建、导入、编辑、配置、版本、权限、诊断、回滚、导出和卸载。
- 现有 Skill 只做一次性迁移，不长期保留 Legacy Adapter 或双 Registry。
- Skill 是当前阶段除不可绕过架构底座外的最高优先级核心修改，必须在 `ARCH-GATE` 前完成并通过 `SKILL-GATE`。

## 目标

1. 编写可实现、可测试的标准 Skill 需求规格。
2. 定义 A Prompt、B Resources、C Executable 兼容等级。
3. 定义统一领域、MySQL/Storage 权威、package 生命周期、capability grant、隔离 runner 和运行固定合同。
4. 定义前端可视化管理、标准内容编辑和无损导出要求。
5. 定义旧内置能力的一次性迁移、观察、切换、回滚和删除清单。
6. 将 `SK-0` 至 `SK-5`、`SKILL-GATE` 和最高优先级同步到架构、路线图、执行、安全和当前架构文档。

## 范围

- 新增 `docs/standard_skill_integration_requirements.md`。
- 更新根 README 和文档索引，准确区分当前私有能力与目标标准能力。
- 更新架构重写计划，将 Skill package 设为 Storage 首个 consumer、worker 首个 workload、AR-5 首个后端域和前端首个功能域。
- 更新路线图和执行计划，把工作包 `11` 从门禁后产品项调整为当前核心必做项。
- 更新安全计划，将当前 Skill 风险登记为 `SKILL-01 P0`。
- 更新当前架构、开发环境和 Agent runtime 文档，标记旧实现为过渡态。
- 建立本目录的 plan、change log 和 test record。

## 非目标

- 不修改 Python、TypeScript、数据库 schema、依赖或部署配置。
- 不实现 parser、Storage、worker、API 或前端页面。
- 不连接、读取、迁移或修改现有 MySQL/Redis/Chroma/用户文件。
- 不删除当前 Skill 目录；实际删除必须等待 SK-5 清单、观察期和回滚证据。
- 不声称任何 `AR-*`、`SK-*`、`SKILL-GATE` 或 `ARCH-GATE` 已完成。

## 执行序列

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

## 风险与控制

| 风险 | 控制 |
|------|------|
| 把“标准格式兼容”误当成“可安全执行” | 分开 `format_compatible/runtime_ready/enabled`，并定义 A/B/C 等级 |
| 为兼容旧系统保留永久双轨 | Legacy 仅允许一次性迁移；SK-5 必须删除运行时旧路径 |
| 前端编辑污染上游或 Git | 不可变版本、结构化写回、Storage 权威和 Git 工作树验收 |
| 为追求优先级跳过安全底座 | 每个 `SK-*` 显式绑定 AR 依赖，依赖缺失时优先补底座 |
| 本机 Node/npm 被当作安全边界 | C 级必须通过独立 runner、资源/网络/secret 授权和强制终止 |

## 回滚

本批次只修改文档。若需求再次调整，可回滚本批次文档并保留历史记录；不得以文档回滚触发代码、数据库或运行数据操作。
