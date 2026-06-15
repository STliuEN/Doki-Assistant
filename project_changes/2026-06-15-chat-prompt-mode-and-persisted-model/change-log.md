# 修改记录

## 后端

- 新增 prompt 文件：
  - `backend/app/prompt/chat_creative_prompt.txt`
  - `backend/app/prompt/chat_strict_prompt.txt`
  - `backend/app/prompt/chat_teacher_prompt.txt`
- 更新 `backend/app/config/prompt.yaml`
  - 注册三个新的 AI 对话 prompt。
- 更新 `backend/app/schemas/models.py`
  - `QueryRequest` 新增 `prompt_type`。
- 更新 `backend/app/router/chat.py`
  - 新增 `GET /chat/prompt-modes`。
  - `/chat/agent/query/stream` 根据 `prompt_type` 加载系统提示词。
- 更新 `backend/app/agent/agent.py`
  - 流式 Agent 支持 `custom_system_prompt` 覆盖默认提示词。

## 前端

- 新增 `front/src/api/chat.ts`
  - 获取 AI 对话模式列表。
- 更新 `front/src/api/endpoints.ts`
  - 新增 `chatPromptModes`。
- 更新 `front/src/pages/AIChat.tsx`
  - 加载 AI 模式。
  - 发送请求时携带 `prompt_type`。
  - 底部模型选择右侧增加 `AI 模式` 下拉框。
  - 使用 `localStorage` 保存 AI 对话模型和 AI 模式。
- 更新 `front/src/pages/RealtimeTranslate.tsx`
  - 使用 `localStorage` 保存实时翻译模型选择。
- 更新 `front/vite.config.ts`
  - 增加 `/chat/prompt-modes` 代理。

## 行为

- 默认 AI 模式为 `默认助手`，即现有 `main_prompt`。
- 用户切换模式后，新消息会使用对应系统提示词。
- 切换页面再回来，模型和 AI 模式不会重置。
