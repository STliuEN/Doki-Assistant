# 记忆中心

记忆中心管理用户的复习、待办、提醒、长期事项和普通备忘，并通过本地 Tool 向 Agent 提供受控读写能力。

## 数据类型

| 类型 | 语义 |
|------|------|
| `review` | 复习、回顾和自测 |
| `todo` | 待办事项 |
| `reminder` | 到期提醒 |
| `long_term` | 长期目标或持续事项 |
| `memo` | 普通备忘 |

记忆中心不是聊天历史的替代品。聊天历史保存对话，知识库/笔记用于内容检索，MemoryItem 保存结构化的个人事项。

## 后端结构

```text
backend/app/models/memory_item.py
backend/app/schemas/memory.py
backend/app/services/memory_service.py
backend/app/router/memory_router.py
```

所有 memory 路由使用 `Depends(get_current_user_id)`，service 查询和修改时必须携带当前 `user_id`。

## API

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/memory/today` | 今日到期或需要处理的事项 |
| GET | `/memory/list` | 按类型、状态等条件列出 |
| POST | `/memory/create` | 创建 |
| GET | `/memory/{memory_id}` | 详情 |
| PUT | `/memory/{memory_id}` | 更新 |
| POST | `/memory/{memory_id}/complete` | 完成 |
| POST | `/memory/{memory_id}/reviewed` | 标记已复习 |
| POST | `/memory/{memory_id}/postpone` | 延期 |
| POST | `/memory/{memory_id}/archive` | 归档 |
| DELETE | `/memory/{memory_id}` | 删除 |
| GET | `/memory/{memory_id}/review-question` | 生成复习问题 |

API 与 Agent Tool 使用同一个 `MemoryService`，避免两套状态变化规则。

## 前端

```text
front/src/pages/MemoryCenter.tsx
front/src/api/memory.ts
front/src/api/endpoints.ts
front/src/types/api.ts
```

当前页面支持：

- 今日、进行中、复习、事项、备忘和已完成视图。
- 新建和编辑。
- 完成、延期、归档和删除。
- 标记已复习和生成复习问题。
- 删除前的前端确认弹窗。

当前没有后台定时扫描或 WebSocket 推送；“今日”数据需要页面请求触发，不是系统级主动提醒。

## Agent Tools

```text
backend/app/agent/tools/
  create_memory/
  list_memories/
  get_memory/
  update_memory/
  delete_memory/
  complete_memory/
  postpone_memory/
  archive_memory/
  mark_memory_reviewed/
  today_reviews/
  generate_review_question/
```

工具通过 `tool_context` 读取当前 `user_id` 和 `session_id`，不接受模型任意指定其他用户身份。

相关 Skills：

```text
backend/app/agent/skills/
  memory_read/
  memory_write/
  memory_cleanup/
  review_planner/
```

Skill 是否进入本轮 Agent 由用户候选选择和意图预路由共同决定。

## 典型调用

```text
“帮我记一下明天下午检查模型配置”
  -> memory_write
  -> create_memory

“今天有什么待办”
  -> memory_read
  -> list_memories or today_reviews

“把刚才那个任务延期到周五”
  -> memory_write
  -> get/list + postpone_memory

“删除这条记忆”
  -> memory_cleanup
  -> delete_memory
  -> waiting_confirmation
```

## 删除安全

`delete_memory` 是需要确认的高风险 Tool：

1. Agent 首次调用时，GuardedTool 不执行删除。
2. 工具参数写入 Redis pending action，默认 TTL 600 秒。
3. SSE 返回 `waiting_confirmation` 和 `pending_action_id`。
4. 用户调用 `POST /chat/agent/confirm` 确认或取消。
5. 确认后按同一 `user_id` 一次性取出动作，并通过 GuardedTool 执行。

前端 API 直接删除与 Agent 删除是两个入口：页面已有确认弹窗，但 API 自身仍会在鉴权后直接执行。需要更严格策略时，应在服务/API 层增加统一的软删除或确认合同。

## 当前存储

MemoryItem 保存在 FastAPI 业务 MySQL database。当前主要通过结构化字段查询：

- user ID。
- memory type。
- status。
- due/review 时间。
- 创建和更新时间。

MemoryItem 尚未写入独立向量索引，因此当前没有真正的语义搜索。Agent 只能使用已有列表、过滤和详情工具组合查找。

## 当前限制

- 没有到期事项后台调度和主动页面推送。
- 不会自动从普通对话、笔记或翻译中提炼候选事项。
- 没有 Memory 语义向量搜索。
- 来源会话/消息/笔记的结构化关联仍不完整。
- 直接 API 删除与 Agent 确认删除的安全体验不同。

对应后续工作见 [全量重构开发计划的前端功能域阶段](./roadmap_next.md#r6-前端功能域重构)。

## 验证

基础语法与服务测试：

```powershell
cd backend
uv run python -m compileall app
uv run pytest tests\test_agent_runtime.py tests\test_agent_run_service.py
```

工具安全回归由 offline smoke benchmark 覆盖：

```powershell
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

人工验证应至少覆盖：

- 两个用户不能读取或修改彼此事项。
- 完成、延期、归档状态正确。
- Agent 删除首次只返回确认，不发生底层删除。
- 确认动作过期、重复消费和跨用户消费均失败。
