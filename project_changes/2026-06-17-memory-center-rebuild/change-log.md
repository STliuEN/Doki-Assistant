# 记忆中心完整重构变更记录

## 后端

- 新增 `backend/app/models/memory_item.py`，统一承载 `review/todo/reminder/long_term/memo`。
- 新增 `backend/app/schemas/memory.py`。
- 新增 `backend/app/services/memory_service.py`，包含通用记忆 CRUD、今日事项查询、延期、归档、完成、复习推进和复习题生成。
- 新增 `backend/app/router/memory_router.py`，提供 `/memory/*` 接口。
- `backend/main.py` 移除 `review_router`，注册 `memory_router`。
- `backend/app/db/db_config.py` 移除 `review_record` 模型导入，加入 `memory_item`。
- `backend/app/services/note_service.py` 将自动复习计划写入 `MemoryItem`，删除笔记时清理对应 review memory。
- `backend/app/router/note_router.py` 更新说明文案。
- `backend/app/prompt/main_prompt.txt` 将每日回顾说明改为记忆中心工具说明。
- 删除旧复习模块：
  - `backend/app/models/review_record.py`
  - `backend/app/services/review_service.py`
  - `backend/app/router/review_router.py`

## Agent

- 新增 memory tools：
  - `create_memory`
  - `list_memories`
  - `complete_memory`
  - `postpone_memory`
  - `mark_memory_reviewed`
- 新增 `backend/app/agent/skills/memory_manager/`。
- 更新 `backend/app/agent/agent_tools.py` 的 legacy exports。
- 删除旧 review tools 和 skill：
  - `today_reviews`
  - `mark_reviewed`
  - `review_planner`

## 前端

- 新增 `front/src/api/memory.ts`。
- 新增 `front/src/pages/MemoryCenter.tsx`。
- `front/src/api/endpoints.ts` 移除 review endpoints，新增 memory endpoints。
- `front/src/types/api.ts` 移除 Review 类型，新增 Memory 类型。
- `front/src/router/index.tsx` 将页面入口改为 `/memory`。
- `front/src/components/layout/Sidebar.tsx` 将侧边栏入口改为记忆中心。
- `front/src/i18n/locales/zh-CN.ts`、`front/src/i18n/locales/en-US.ts` 更新导航与描述文案。
- `front/vite.config.ts` 将 dev proxy 从 `/review/` 改为 `/memory/`。
- 删除旧前端复习模块：
  - `front/src/api/review.ts`
  - `front/src/pages/DailyReview.tsx`

