# 复习计划

管理间隔复习（review 类型）：今日复习、推进进度、生成自测题。

- “今天复习什么/待复习” → today_reviews_tool。
- 已知复习项 ID 查看内容 → get_memory_tool；找候选 → list_memories_tool(type=review)。
- 用户完成复习 → mark_memory_reviewed_tool（推进 1/2/4/7/15/30 天间隔，仅 review 类型）。
- 自测/检查掌握 → generate_review_question_tool。
- 暂时不想复习 → postpone_memory_tool。
- 缺少明确 ID 时先列候选确认。
- 用户要新建复习项时，属“记录与变更”能力（create_memory）。
