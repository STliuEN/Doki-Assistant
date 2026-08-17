# 改进执行选择

状态：待选择
最近复核：2026-08-17
适用范围：当前 `ai_document_assistant` 分支

本文把 [全量重构开发计划](./roadmap_next.md) 和 [安全与可靠性加固计划](./security_hardening_plan.md) 转换为可独立执行、验收和回滚的工作包。主计划继续维护阶段依赖，安全计划继续维护风险细节；本文只回答“下一项具体做什么”。

## 当前验证基线

| 检查 | 2026-08-17 结果 |
|------|-----------------|
| Backend pytest | 82 passed |
| Backend CI 范围 Ruff | passed |
| FastAPI OpenAPI | current |
| Django system check | passed |
| Django tests | 0 tests |
| Markdown | 117 个文件、73 个本地链接通过 |
| Offline Benchmark | smoke 4/4，regression 117/117 |
| Frontend 本机复核 | 未运行；当前主机没有可用的 `npm` |

这些结果证明现有 Agent 回归面稳定，但不覆盖目录穿越、浏览器内容安全、完整 token 生命周期、数据库迁移和真实浏览器主流程。

## 选择方式

- 回复一个序号时，只执行该工作包，例如 `1`。
- 回复多个序号时，按依赖顺序执行，例如 `1,2`。
- 默认推荐从 `1` 开始；涉及数据库或身份源切换的工作包不与其他高风险迁移并行。
- 每个序号单独建立 `project_changes/<date>-<topic>/`，包含 plan、change log 和 test record。
- 完成一个序号后更新本文状态，不把未完成工作标记为完成。

## 可选工作包

| 序号 | 工作包 | 优先级 | 主要范围 | 前置依赖 | 核心验收 |
|------|--------|--------|----------|----------|----------|
| 1 | 知识库路径 containment | P0 | 统一安全路径 helper；校验 MD5、文件名、扩展名、根目录和批量读取预算 | 无 | 反斜杠、编码路径、绝对路径、盘符、跨用户和 reparse point 测试通过 |
| 2 | 聊天安全渲染 | P0 | 移除 `rehypeRaw`，或引入最小白名单 sanitizer；统一流式和历史消息渲染 | 无 | script、事件属性、iframe、危险 URL 无法执行，Markdown 正常能力不回归 |
| 3 | Token 生命周期与前端认证状态 | P0 | 区分 access/refresh token；固定最大寿命和轮换；检查用户状态与 token version；确定 Redis 撤销键；前端只保留一个认证来源 | 2 | 过期、锁定、注销、改密、重复刷新、Redis 故障和 401 清理测试通过 |
| 4 | 部署与鉴权可靠性 | P0/P1 | 移除默认固定账号；增加 dev/prod profile、CORS allowlist 和接口限流；把异步鉴权中的同步 `requests` 改为有超时的异步 client | 无，建议在 3 后 | production 配置 fail fast；Django 超时不会阻塞事件循环；默认启动不创建已知凭据 |
| 5 | 版本化数据库迁移 | P0 | 跟踪 Django migration；引入 Alembic baseline；停止启动期 `makemigrations`、`create_all` 和自动补列 | 1-4 建议完成 | 空库和现有库可重复升级；有备份、dry-run、回滚和 CI migration gate |
| 6 | API 合同与特征测试 | P1 | `ApiResponse[T]`、SSE schema、认证状态码合同、Django 用户测试、跨服务认证测试和关键 Playwright 主流程 | 1-3 | OpenAPI 与真实响应一致；核心用户流程成为 required checks |
| 7 | 回答引用与一键沉淀 | Feature | SSE 返回文档、页码、chunk 和得分；前端来源抽屉；回答可保存为笔记或记忆并保留来源 | 2、6 | 引用可跳回原文；保存结果可追溯到会话和来源；越权来源不可见 |
| 8 | 知识处理任务中心 | Feature | 持久化 queued/processing/ready/failed/cancelled；幂等上传、进度、取消和重试 | 5、6 | 进程重启后状态可恢复；重复重试不产生重复向量或孤立文件 |
| 9 | 统一搜索 | Feature | 跨笔记、记忆、会话和知识库检索；类型、时间、标签和来源过滤 | 5、6 | 结果严格按用户隔离；可从结果进入原对象；混合检索有质量基线 |
| 10 | 运行追踪、导出与恢复 | P1/Feature | Agent run、模型/Tool/耗时/错误记录；版本化数据导出；备份恢复和部署演练 | 3、5、6 | run 可诊断；导出可校验；数据库、文件和向量状态可恢复 |

## 默认顺序

```text
1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10
```

`1-4` 建立可信安全边界，`5-6` 建立可迁移和可测试基础，`7-10` 才扩展产品闭环。若只选择一个新功能，优先选择 `7`；它直接增强知识助手的可验证性，但仍必须先满足其前置依赖。

## 完成定义

每个工作包只有同时满足以下条件才可关闭：

1. 失败测试或 characterization test 先于实现落地。
2. 相关 unit、API、frontend、build、OpenAPI 和 Benchmark gate 通过。
3. 数据、文件、权限和外部网络边界经过复核。
4. 有回滚方法，且不覆盖用户现有未提交修改或本机配置。
5. 同步更新活文档，并在 `project_changes/` 保存执行证据。
