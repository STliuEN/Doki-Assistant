# 工作计划与代码现实校准

日期：2026-08-25

状态：计划文档修订中；业务实现未修改；任何 AR/SK 门禁均未通过

## 目标

根据当前分支代码、依赖、CI 和可重复测试结果，修正架构重写、路线图、执行计划与标准 Skill 计划中的状态漂移、循环依赖和不可达门禁，形成一条可实际执行的本地主线。

## 范围

- 将 `docs/architecture_rewrite_plan.md` 固定为 AR/SK 状态、依赖和门禁的唯一事实源。
- 把当前停留点改为 `AR-0 + SK-0`，记录已有切片和未通过的退出门。
- 把 Chroma 破坏性 reset、Skill 发布原子性、Registry 单包隔离、授权/撤销/审计、Tool/MCP policy 权威和 Skill OpenAPI 合同列为 durable worker 前的阻断项。
- 明确 AR-1 只交付通用 durable job/UoW/隔离进程协议，SK-4 才交付 Node/Python adapter，消除循环依赖。
- 将本地 A/B `SKILL-GATE`、本地 `ARCH-GATE`、可选 `EXEC-SKILL-GATE` 和公网 `PUBLIC-HA-GATE` 分开。
- 把真实依赖集成环境和 R7 测试入口前置到 AR-0，把 per-user scope、预算、真实 A/B E2E 和迁移影子对账放回其真实依赖之后。
- 同步路线图、执行计划、标准 Skill 规格和本轮 Skill 变更计划，撤回无法由当前代码证明的完成声明。

## 非目标

- 不修改 Python、TypeScript、PowerShell、workflow、依赖或数据库 schema。
- 不修复本次审阅发现的业务代码问题；它们成为后续实现批次的明确入口。
- 不连接或修改 MySQL、Redis、Storage、Chroma 和用户数据。
- 不声明 Linux、C 级执行、公网或 HA 支持。

## 回滚

本批仅修改 Markdown。若计划修订引入冲突，回滚本目录记录和对应活文档即可；不得以恢复 Legacy runtime 或删除数据作为文档回滚手段。

## 完成条件

- 活文档只有一份阶段状态与当前执行顺序。
- `AR-0 -> AR-1 -> AR-2/3 -> AR-4/5` 依赖无循环，Skill import 是首个 worker consumer。
- 本地 A/B、C 级执行与公网 HA 的门禁范围互不冒充。
- 当前代码的已知阻断和验证缺口在计划中有对应工作包与退出证据。
- 文档链接、围栏、scoped whitespace check 和事实源引用检查通过。
