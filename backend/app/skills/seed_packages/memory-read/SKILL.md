---
name: memory-read
description: "查看、浏览、列出已有的待办提醒事项清单与单条详情，只读不修改。"
---
# 记忆事项 · 查询

查看今日事项、按类型浏览、查看单条详情，只读不改。

- “今天有什么/有哪些待办/提醒/长期事项” → list_memories_tool（scope 取 today 或 all，可按 type 过滤）。
- 查看某条完整详情 → get_memory_tool（需事项 ID）。
- 涉及相对日期用 what_time_is_now 换算。
- 本能力不创建、不修改、不删除事项。
