# 记忆中心当前实现与后续计划

记忆中心已经替代旧的每日回顾主链路，成为统一管理复习、待办、提醒、长期事项和普通备忘的模块。本文记录当前实现、接口、Agent tools 和下一步闭环方向。

## 当前定位

记忆中心负责管理用户的个人事项与复习记忆：

- `review`：笔记复习和自测。
- `todo`：待办事项。
- `reminder`：提醒。
- `long_term`：长期事项。
- `memo`：普通备忘。

它不是单独的复习页面，而是 Agent 可以读写的长期任务/记忆底座。

## 当前后端实现

核心文件：

```text
backend/app/models/memory_item.py
backend/app/schemas/memory.py
backend/app/services/memory_service.py
backend/app/router/memory_router.py
```

主要接口：

```text
GET    /memory/today
GET    /memory/list
POST   /memory/create
GET    /memory/{memory_id}
PUT    /memory/{memory_id}
POST   /memory/{memory_id}/complete
POST   /memory/{memory_id}/reviewed
POST   /memory/{memory_id}/postpone
POST   /memory/{memory_id}/archive
DELETE /memory/{memory_id}
GET    /memory/{memory_id}/review-question
```

所有正式 memory 接口都通过 `Depends(get_current_user_id)` 使用当前登录用户，服务层按 `user_id` 查询和修改。

## 当前前端实现

核心文件：

```text
front/src/api/memory.ts
front/src/pages/MemoryCenter.tsx
front/src/api/endpoints.ts
front/src/types/api.ts
```

页面已支持：

- 今日事项
- 进行中
- 复习
- 事项
- 备忘
- 已完成
- 新建 memory
- 完成
- 延期
- 归档
- 删除
- 复习题生成
- 标记已复习

前端删除 memory 当前有确认弹窗，但还没有和 Agent 高风险工具确认机制打通。

## 当前 Agent Tools

当前已存在记忆相关工具：

```text
backend/app/agent/tools/create_memory/
backend/app/agent/tools/list_memories/
backend/app/agent/tools/get_memory/
backend/app/agent/tools/update_memory/
backend/app/agent/tools/delete_memory/
backend/app/agent/tools/complete_memory/
backend/app/agent/tools/postpone_memory/
backend/app/agent/tools/archive_memory/
backend/app/agent/tools/mark_memory_reviewed/
```

这些工具通过 `tool_context` 读取当前 `user_id`，避免模型直接决定用户身份。

相关 Skill：

```text
backend/app/agent/skills/memory_read/
backend/app/agent/skills/memory_write/
backend/app/agent/skills/memory_cleanup/
```

当前 skill 预路由会根据用户意图选中 memory read/write/cleanup 类能力。

## 当前可用场景

示例：

```text
“帮我记一下明天下午检查模型配置”
  -> create_memory

“今天有什么要做”
  -> list_memories

“这个事项完成了”
  -> complete_memory

“今天有什么要复习”
  -> list_memories(type=review)

“这条复习完成了”
  -> mark_memory_reviewed
```

## 当前不足

### 1. 缺主动提醒

后端能查今日事项，但没有后台扫描任务，也没有页面级主动提醒推送。

### 2. 缺自动提炼

Agent 只有在用户明确要求“记一下 / 提醒我 / 加待办”时才写入 memory。普通对话、RAG 回答、翻译结果还不会自动提炼待办或提醒。

### 3. 缺高风险确认

`delete_memory` 属于高风险工具。当前只靠 prompt 和前端手动删除确认，Agent 调用删除工具前没有统一二次确认。

### 4. 缺语义搜索

memory 当前主要按类型、状态、时间查询。还没有把 memory 写入向量库做语义召回。

### 5. 旧复习文案仍需继续清理

部分文档、i18n 或历史变更记录里可能仍出现“每日回顾”。历史记录可以保留，但正式产品入口应统一为“记忆中心”。

## 下一步计划

### P1.1 主动提醒

目标：

- 后端定时扫描到期 `reminder/todo/review`。
- 前端页面内提示。
- 预留桌面端系统通知。

验收：

- 到期事项不用用户主动刷新也能提示。
- 完成、延期后不再重复提醒。

### P1.2 对话后事项提炼

目标：

- 对话结束后提炼“可能保存的事项”。
- 只展示建议，不自动写入。
- 用户确认后调用 memory API 创建。

来源：

- AI 对话
- RAG 总结
- 笔记内容
- 实时翻译结果

验收：

- 用户能从一次对话中一键保存待办/提醒/长期事项。
- 提炼错误时不会污染 memory。

### P1.3 Memory 语义搜索

目标：

- 将 memory 内容写入向量索引。
- 支持“我之前说过什么待办”“找一下关于模型配置的提醒”。

验收：

- Agent 可以通过语义查询找回相关 memory。
- 仍然按当前 user_id 隔离。

### P1.4 高风险操作确认

目标：

- 给 `delete_memory` 标记 `risk_level=high`。
- Agent 调用删除前进入确认状态。
- 用户确认后才执行。

该项依赖 [Agent 运行时改进评估](./agent_runtime_improvements.md) 中的高风险工具确认机制。

## 验收命令

后端：

```powershell
cd backend
uv run python -m compileall app
```

前端：

```powershell
cd front
npm run build
```

旧引用检查：

```powershell
rg -n "DailyReview|review_router|review_service|ReviewRecord|reviewApi|/review" backend front
```

说明：`review_question_prompt.txt` 和历史文档中出现 review 属于正常情况；业务入口不应继续依赖旧 review router/service/page。

