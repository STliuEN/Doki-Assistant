---
name: memory-write
description: "新建、创建、登记、记下提醒待办事项；以及对已有事项做完成、修改、更新、延期、推迟。"
---
# 记忆事项 · 记录与变更

创建新事项，或对已有事项做完成、修改、延期。

- 记录/提醒/待办/“下周再看”/加入复习 → create_memory_tool（type 取 todo/reminder/long_term/memo/review；相对时间先用 what_time_is_now 换算为具体日期）。
- 完成某条（非复习类）→ complete_memory_tool。
- 修改标题/内容/类型/状态/优先级/时间 → update_memory_tool。
- 推迟到期 → postpone_memory_tool。
- 需要先定位目标时，用 list_memories_tool / get_memory_tool 查 ID；缺少明确 ID 时先列候选请用户确认，不要猜测。
- 归档与永久删除不在本能力范围。
