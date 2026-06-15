# AI 对话组合 Prompt 计划

## 问题

AI 模式切换后看起来仍然像只使用主 prompt。直接替换 `main_prompt` 也会让 Agent 丢失工具、RAG、笔记管理等基础规则。

## 目标

改成组合 prompt：

- 默认模式：只使用 `main_prompt`。
- 其他模式：使用 `main_prompt + 模式补充 prompt`。

这样既保留 Agent 基础能力，又能通过模式 prompt 改变回答风格。

## 计划

1. 后端新增 `build_chat_system_prompt`。
2. 校验 `prompt_type` 后构建组合提示词。
3. Agent 继续通过 `custom_system_prompt` 接收最终组合 prompt。
4. 前端请求结构不变，继续传 `prompt_type`。
