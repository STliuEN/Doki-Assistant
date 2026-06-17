# 记忆中心完整重构计划

## 目标

将原“每日回顾 / 复习模块”完整重构为“记忆中心”。复习不再作为独立模块存在，而是作为 `MemoryItem.type = review` 的同级记忆类型，与待办、提醒、长期事项和普通备忘统一管理。

## 范围

- 新增统一记忆模型、服务、路由和前端页面。
- 移除旧 `/review/*` 后端正式接口。
- 删除旧 `ReviewRecord`、`review_service`、`review_router`。
- 删除旧 `reviewApi` 和 `DailyReview` 页面。
- 删除旧 Agent `today_reviews`、`mark_reviewed` 工具和 `review_planner` skill。
- 新增 memory tools 和 `memory_manager` skill。
- 笔记自动复习计划改为写入 `memory_items`。

## 非目标

- 不做旧 `review_records` 自动迁移。
- 不做系统通知或桌面通知。
- 不做自动从全部聊天中提炼记忆事项。
- 不改 RAG、翻译和模型配置主链路。

