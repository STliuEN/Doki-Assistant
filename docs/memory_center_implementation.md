# 记忆中心完整重构实操文档

本文档用于指导把现有“每日回顾 / 复习模块”完整重构为“记忆中心”。本次不做兼容过渡：复习不再作为独立模块存在，而是作为记忆中心中的一种同级记忆类型，与待办、提醒、长期事项、普通备忘一起由统一模型、统一服务、统一接口、统一前端页面和统一 Agent 工具管理。

## 1. 重构目标

本次重构完成后，系统应满足：

- 删除独立复习模块的业务主链路。
- 使用统一模型 `MemoryItem` 管理所有个人记忆事项。
- `review`、`todo`、`reminder`、`long_term`、`memo` 是同级类型。
- 复习的间隔算法迁入 `memory_service`。
- 新建笔记后自动创建 `type = review` 的记忆事项。
- 记忆中心页面替代每日回顾页面。
- Agent 通过统一 memory tools 创建、查询、完成和推进复习事项。
- 不再保留 `/review/*` 作为正式接口。

## 2. 删除与替换范围

本次是完整重构，以下旧模块不再作为业务入口：

```text
backend/app/models/review_record.py
backend/app/services/review_service.py
backend/app/router/review_router.py
front/src/api/review.ts
front/src/pages/DailyReview.tsx
backend/app/agent/tools/today_reviews/
backend/app/agent/tools/mark_reviewed/
backend/app/agent/skills/review_planner/
```

可以选择直接删除这些文件，也可以先在同一提交中移除所有引用后删除。不要留下继续被调用的旧接口或旧工具。

替换为：

```text
backend/app/models/memory_item.py
backend/app/services/memory_service.py
backend/app/router/memory_router.py
front/src/api/memory.ts
front/src/pages/MemoryCenter.tsx
backend/app/agent/tools/create_memory/
backend/app/agent/tools/list_memories/
backend/app/agent/tools/complete_memory/
backend/app/agent/tools/postpone_memory/
backend/app/agent/tools/mark_memory_reviewed/
backend/app/agent/skills/memory_manager/
```

## 3. 推荐施工顺序

1. 全局搜索旧复习引用，确认影响面。
2. 新增 `MemoryItem` 模型。
3. 从数据库建表导入中移除 `review_record`，加入 `memory_item`。
4. 新增 `memory_service`，实现复习算法和通用记忆操作。
5. 新增 `/memory/*` 路由，并移除 `/review/*` 路由注册。
6. 修改笔记创建后的自动复习计划生成逻辑，写入 `MemoryItem`。
7. 新增前端 `memoryApi`、类型和 `MemoryCenter` 页面。
8. 从路由和侧边栏中移除 `DailyReview`，改为记忆中心。
9. 删除旧 Agent review tools，新增 memory tools。
10. 删除或替换 `review_planner` skill，新增 `memory_manager`。
11. 跑后端编译、前端构建和关键手工验收。
12. 补充 `project_changes` 记录。

## 4. 后端模型

新增：

```text
backend/app/models/memory_item.py
```

建议模型：

```python
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.models.chat_history import Base


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id = Column(String(36), primary_key=True, comment="UUID")
    user_id = Column(String(36), index=True, nullable=False, comment="用户ID")

    source_type = Column(String(32), default="manual", index=True, comment="manual/chat/note/translate/rag")
    source_id = Column(String(36), nullable=True, index=True, comment="来源对象ID")

    type = Column(String(32), default="memo", index=True, comment="review/todo/reminder/long_term/memo")
    title = Column(String(255), nullable=False, comment="标题")
    content = Column(Text, nullable=True, comment="内容")
    status = Column(String(32), default="active", index=True, comment="active/done/archived")
    priority = Column(String(32), default="medium", index=True, comment="low/medium/high")

    due_at = Column(DateTime(timezone=True), nullable=True, index=True, comment="到期时间")
    remind_at = Column(DateTime(timezone=True), nullable=True, index=True, comment="提醒时间")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    archived_at = Column(DateTime(timezone=True), nullable=True, comment="归档时间")

    review_count = Column(Integer, default=0, comment="复习次数，仅 review 类型使用")
    interval_days = Column(Integer, default=1, comment="当前复习间隔，仅 review 类型使用")

    metadata_json = Column(Text, nullable=True, comment="扩展元数据JSON")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
```

修改：

```text
backend/app/models/__init__.py
backend/app/db/db_config.py
```

要求：

- 移除 `review_record` 的模型导入。
- 加入 `memory_item` 的模型导入。
- 确保启动建表时能创建 `memory_items`。

如果本地数据库已有 `review_records` 表，本次重构不负责历史迁移。开发环境可以手动清理旧表或保留闲置表，但代码层不再依赖它。

## 5. 后端 Schema

新增：

```text
backend/app/schemas/memory.py
```

建议结构：

```python
from datetime import datetime
from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    type: str = Field(default="memo")
    title: str
    content: str | None = None
    priority: str = "medium"
    due_at: datetime | None = None
    remind_at: datetime | None = None
    source_type: str = "manual"
    source_id: str | None = None
    metadata_json: str | None = None


class MemoryUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    content: str | None = None
    status: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    remind_at: datetime | None = None
    metadata_json: str | None = None


class MemoryPostpone(BaseModel):
    days: int = 1
```

第一阶段可以先用字符串类型。等功能稳定后，再收紧为枚举。

## 6. 后端服务

新增：

```text
backend/app/services/memory_service.py
```

需要实现：

```text
create_memory(db, user_id, payload)
create_review_for_note(db, user_id, note_id, title, content_preview)
list_memories(db, user_id, type=None, status=None)
get_today_memories(db, user_id)
get_memory(db, user_id, memory_id)
update_memory(db, user_id, memory_id, payload)
complete_memory(db, user_id, memory_id)
postpone_memory(db, user_id, memory_id, days)
archive_memory(db, user_id, memory_id)
delete_memory(db, user_id, memory_id)
mark_reviewed(db, user_id, memory_id)
generate_review_question(db, user_id, memory_id)
```

复习间隔算法迁入本服务：

```python
INTERVALS = [1, 2, 4, 7, 15, 30]


def get_next_review_interval(review_count: int) -> int:
    if review_count < len(INTERVALS):
        return INTERVALS[review_count]
    return INTERVALS[-1]
```

`complete_memory` 规则：

- 非 `review` 类型：设置 `status = done`、`completed_at = now`。
- `review` 类型：不要使用 `complete_memory` 推进复习，应返回明确错误，提示调用 `mark_reviewed`。

`mark_reviewed` 规则：

- 仅允许处理 `type = review` 的事项。
- `review_count += 1`
- `interval_days = get_next_review_interval(review_count)`
- `due_at = now + interval_days`
- `remind_at = due_at`
- `status = active`
- 不设置 `completed_at`

`get_today_memories` 查询：

```text
user_id = 当前用户
status = active
due_at <= now 或 remind_at <= now
按 priority、due_at、created_at 排序
```

`generate_review_question`：

- 输入 `memory_id`。
- 校验该 memory 属于当前用户且 `type = review`。
- 优先使用 `content`。
- 如果 `source_type = note` 且内容不足，可以查询对应 Note 内容。
- 复用原来的 `review_question_prompt`。

## 7. 笔记服务改造

需要找到当前保存笔记后创建复习记录的位置。重点检查：

```text
backend/app/services/note_service.py
backend/app/router/note_router.py
```

把原先创建 `ReviewRecord` 的逻辑替换为：

```python
await memory_service.create_review_for_note(
    db=db,
    user_id=user_id,
    note_id=note.id,
    title=note.title,
    content_preview=(note.content or "")[:200],
)
```

`create_review_for_note` 默认：

```text
type = review
source_type = note
source_id = note_id
title = note title
content = content preview
status = active
priority = medium
review_count = 0
interval_days = 1
due_at = now + 1 day
remind_at = due_at
```

删除笔记时，原来如果依赖外键级联删除 `review_records`，现在需要显式删除或清理对应 memory：

```text
source_type = note
source_id = note_id
type = review
```

## 8. 后端路由

新增：

```text
backend/app/router/memory_router.py
```

正式接口：

```text
GET    /memory/today
GET    /memory/list
GET    /memory/{memory_id}
POST   /memory/create
PUT    /memory/{memory_id}
POST   /memory/{memory_id}/complete
POST   /memory/{memory_id}/reviewed
POST   /memory/{memory_id}/postpone
POST   /memory/{memory_id}/archive
DELETE /memory/{memory_id}
GET    /memory/{memory_id}/review-question
```

要求：

- 全部接口必须带当前用户校验。
- 不再新增或保留正式 `/review/*` 接口。
- 从后端 app/router 注册处移除 `review_router`。
- 加入 `memory_router`。

响应格式沿用项目现有 `success_response`。

## 9. 前端类型与 API

修改：

```text
front/src/api/endpoints.ts
front/src/types/api.ts
```

删除：

```text
front/src/api/review.ts
```

新增：

```text
front/src/api/memory.ts
```

类型建议：

```ts
export type MemoryType = 'review' | 'todo' | 'reminder' | 'long_term' | 'memo'
export type MemoryStatus = 'active' | 'done' | 'archived'
export type MemoryPriority = 'low' | 'medium' | 'high'

export interface MemoryItem {
  id: string
  source_type?: string
  source_id?: string
  type: MemoryType
  title: string
  content?: string
  status: MemoryStatus
  priority: MemoryPriority
  due_at?: string | null
  remind_at?: string | null
  completed_at?: string | null
  archived_at?: string | null
  review_count?: number
  interval_days?: number
  created_at?: string
  updated_at?: string
}

export interface MemoryQuestion {
  question: string
  choices: string[]
  answer: string
}
```

`memoryApi` 方法：

```ts
today()
list(params?)
get(id)
create(payload)
update(id, payload)
complete(id)
reviewed(id)
postpone(id, days)
archive(id)
delete(id)
getReviewQuestion(id)
```

## 10. 前端页面

删除旧页面入口：

```text
front/src/pages/DailyReview.tsx
```

新增：

```text
front/src/pages/MemoryCenter.tsx
```

修改：

```text
front/src/router/index.tsx
front/src/components/layout/Sidebar.tsx
front/src/i18n/locales/zh-CN.ts
front/src/i18n/locales/en-US.ts
```

路由建议：

```text
/memory
```

如果希望侧边栏位置不变，也可以让原 `/review` 改为 `/memory`，但不要继续命名为 DailyReview。

页面第一版功能：

- 顶部：记忆中心标题、新建按钮。
- 筛选：今日、全部、复习、待办、提醒、长期事项、普通备忘、已完成。
- 列表：显示统一 `MemoryItem`。
- 新建弹窗：选择类型、标题、内容、优先级、到期时间。
- 普通事项操作：完成、延期、归档、删除。
- 复习事项操作：开始复习、重新生成题目、标记已复习。

复习题逻辑不再调用 `reviewApi`，而是：

```text
memoryApi.getReviewQuestion(memoryId)
memoryApi.reviewed(memoryId)
```

渲染分支：

```tsx
if (item.type === 'review') {
  // 题目、选项、标记已复习
} else {
  // 完成、延期、归档
}
```

## 11. Agent 工具

删除旧工具：

```text
backend/app/agent/tools/today_reviews/
backend/app/agent/tools/mark_reviewed/
```

新增工具：

```text
backend/app/agent/tools/create_memory/
backend/app/agent/tools/list_memories/
backend/app/agent/tools/complete_memory/
backend/app/agent/tools/postpone_memory/
backend/app/agent/tools/mark_memory_reviewed/
```

每个工具目录包含：

```text
__init__.py
tool.py
tool.yaml
TOOL.md
```

工具设计：

```text
create_memory_tool(title, content="", type="memo", priority="medium", due_at=None)
list_memories_tool(scope="today", type=None, status="active")
complete_memory_tool(memory_id)
postpone_memory_tool(memory_id, days=1)
mark_memory_reviewed_tool(memory_id)
```

规则：

- 创建复习类型一般由笔记服务自动完成，Agent 默认不要随便创建 `review`，除非用户明确要求“把这条内容加入复习”。
- `complete_memory_tool` 不处理 review。
- `mark_memory_reviewed_tool` 只处理 review。
- 工具输出要包含 memory id，方便用户后续引用。

## 12. Agent Skill

删除或替换：

```text
backend/app/agent/skills/review_planner/
```

新增：

```text
backend/app/agent/skills/memory_manager/
```

`skill.yaml` 示例：

```yaml
id: memory_manager
label: 记忆与事项管理
description: 管理复习、待办、提醒、长期事项和普通备忘。
tools:
  - current_time
  - create_memory
  - list_memories
  - complete_memory
  - postpone_memory
  - mark_memory_reviewed
default: true
order: 60
```

`SKILL.md` 要点：

- 用户说“提醒我”“记一下”“加入待办”“下周再看”时，创建 memory。
- 用户问“今天有什么事”“有哪些待办”“今天要复习什么”时，查询 memory。
- 用户说“完成了”时，根据上下文选择完成普通事项或推进复习事项。
- 对 `review` 类型使用 `mark_memory_reviewed`。
- 对非 `review` 类型使用 `complete_memory`。
- 涉及相对日期时，先结合当前时间转换为明确日期。

## 13. 全局引用清理

必须用 `rg` 检查并清理：

```powershell
rg -n "review_router|review_service|ReviewRecord|reviewApi|DailyReview|today_reviews|mark_reviewed|review_planner|/review" backend front
```

处理原则：

- `review_question_prompt.txt` 可以保留，因为它是复习题提示词，不是旧模块入口。
- 文档或变更日志中的历史描述可以保留。
- 业务代码中不应再引用旧 review service/router/model/api/page/tool/skill。

## 14. 验收清单

后端：

- 启动后能创建 `memory_items` 表。
- `/memory/create` 可以创建 todo/reminder/memo。
- `/memory/today` 可以返回今日到期事项。
- `/memory/{id}/complete` 可以完成非 review 事项。
- `/memory/{id}/reviewed` 可以推进 review 事项的下次复习时间。
- `/memory/{id}/review-question` 可以为 review 事项生成题目。
- 新建笔记后自动创建 `type = review` 的 memory。
- 删除笔记后对应 review memory 被删除或不再出现在列表。
- `/review/*` 不再作为正式接口存在。

前端：

- 侧边栏显示“记忆中心”。
- 进入 `/memory` 能看到今日事项。
- 可以新建待办、提醒、普通备忘。
- 普通事项可以完成、延期、归档、删除。
- 复习事项可以生成题目并标记已复习。
- 原 `DailyReview` 页面不再作为路由入口。

Agent：

- “帮我记一下明天下午检查模型配置”能创建 reminder。
- “今天有什么要做”能列出今日 memory。
- “这个事项完成了”能完成普通事项。
- “今天有什么要复习”能列出 review memory。
- “这条复习完成了”能推进 review memory。

回归：

- AI Chat 正常流式回复。
- 笔记创建、编辑、删除正常。
- 知识库上传和检索不受影响。
- 实时翻译不受影响。
- Skill/Tool 管理页能正常显示新 memory tools 和 memory skill。

## 15. 测试命令

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

全局旧引用检查：

```powershell
rg -n "review_router|review_service|ReviewRecord|reviewApi|DailyReview|today_reviews|mark_reviewed|review_planner|/review" backend front
```

## 16. 变更记录建议

新增目录：

```text
project_changes/2026-06-17-memory-center-rebuild/
```

建议包含：

```text
plan.md
change-log.md
test-record.md
```

`plan.md` 记录完整重构范围；`change-log.md` 记录删除、替换和新增文件；`test-record.md` 记录编译、构建、接口和页面验证结果。

## 17. 后续阶段

本次完整重构完成后，再考虑：

- 从聊天中自动提炼 memory。
- 从实时翻译会议记录中提炼待办和术语。
- 加系统通知或桌面通知。
- 加周期性提醒。
- 加 memory 语义搜索。
- 把长期事项与 RAG、笔记关联推荐打通。

