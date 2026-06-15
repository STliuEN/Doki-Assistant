# 修改记录

## 后端

- 更新 `backend/app/router/chat.py`
  - 新增 `build_chat_system_prompt(prompt_type)`。
  - `main_prompt` 模式只返回基础 prompt。
  - 非默认模式返回：
    - `main_prompt`
    - 当前 AI 模式补充 prompt
    - 冲突处理说明
  - `/chat/agent/query/stream` 改为使用组合 prompt。

## 前端

- 前端请求不需要变化，仍然通过 `prompt_type` 选择模式。

## 行为

- Agent 的 RAG、工具、笔记管理规则永远来自 `main_prompt`。
- 创意、严谨、教学等模式作为补充规则追加到基础规则后。
- 风格模式不会破坏基础工具能力。
