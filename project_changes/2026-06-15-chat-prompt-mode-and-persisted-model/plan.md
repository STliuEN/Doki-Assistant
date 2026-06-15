# AI 对话模式和模型选择持久化计划

## 目标

1. AI 对话右侧增加 `AI 模式` 选择。
2. 默认模式仍然使用现有角色提示词。
3. 用户可以切换已有提示词来切换回答风格。
4. 保存每次选择的模型，切换页面后不需要重新选择。

## 后端计划

- 增加 AI 对话专用 prompt：
  - 创意伙伴
  - 严谨助手
  - 教学助手
- 保留 `main_prompt` 作为默认助手。
- `QueryRequest` 增加 `prompt_type`。
- 新增 `GET /chat/prompt-modes` 返回可选模式。
- `/chat/agent/query/stream` 根据 `prompt_type` 加载不同系统提示词。

## 前端计划

- AI 对话页加载 prompt 模式列表。
- 底部模型选择右侧增加 `AI 模式` 下拉框。
- 发送对话时携带 `prompt_type`。
- 使用 `localStorage` 保存：
  - AI 对话模型选择
  - AI 对话模式选择
  - 实时翻译模型选择
