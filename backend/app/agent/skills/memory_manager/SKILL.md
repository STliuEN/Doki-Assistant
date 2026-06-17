# 事项与备忘管理

管理待办、提醒、长期事项、普通备忘（todo/reminder/long_term/memo）的全生命周期。

- 记录/提醒/待办/“下周再看” → create_memory_tool（相对时间先用 what_time_is_now 换算）。
- 查看今日或某类事项 → list_memories_tool；查看单条详情 → get_memory_tool。
- 修改标题/内容/类型/状态/优先级/时间 → update_memory_tool。
- 完成事项 → complete_memory_tool（不适用于复习类）。
- 推迟 → postpone_memory_tool；保留但不再展示 → archive_memory_tool；永久删除 → delete_memory_tool（仅用户明确要求）。
- 缺少明确事项 ID 时，先用 list_memories_tool 列候选请用户确认，不要猜测。
- 复习推进、今日复习、出题属于“复习计划”能力。
