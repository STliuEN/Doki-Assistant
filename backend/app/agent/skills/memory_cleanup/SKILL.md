# 记忆事项 · 清理（归档/删除）

归档或永久删除事项，仅在用户明确要求时执行。

- 保留记录但不再展示 → archive_memory_tool。
- 永久删除、不可恢复 → delete_memory_tool。
- 必须有明确事项 ID；缺 ID 时用 list_memories_tool / get_memory_tool 列候选并请用户确认，绝不猜测要操作哪一条。
- 用户没有明确的归档/删除意图时，不要主动执行。
