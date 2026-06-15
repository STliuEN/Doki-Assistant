# 修改记录

## 后端

- 新增 `backend/app/prompt/bidirectional_translate_prompt.txt`
  - 使用中文 prompt。
  - 定义双语互译规则。
  - 要求逐行判断语言并翻译为另一种语言。
- 更新 `backend/app/config/prompt.yaml`
  - 注册 `bidirectional_translate_prompt`。
- 新增 `backend/app/schemas/translate.py`
  - 定义 `DialogueTranslateRequest`。
- 新增 `backend/app/services/translate_service.py`
  - 复用 `create_chat_model_from_config`。
  - 支持工程默认模型和用户模型配置。
  - 通过 SSE 输出翻译结果。
- 新增 `backend/app/router/translate.py`
  - 提供 `POST /translate/dialogue/stream`。
  - 校验语言、文本和模型配置。
- 更新 `backend/main.py`
  - 注册 `translate_router`。

## 前端

- 新增 `front/src/pages/RealtimeTranslate.tsx`
  - 提供双栏实时翻译工作台。
  - 支持语言选择、模型选择、交换语言、复制、清空、保存笔记。
- 新增 `front/src/api/translate.ts`
  - 暴露翻译 SSE endpoint。
- 更新 `front/src/api/endpoints.ts`
  - 新增 `dialogueTranslateStream`。
- 更新 `front/src/router/index.tsx`
  - 新增 `/translate` 路由。
- 更新 `front/src/components/layout/Sidebar.tsx`
  - 新增“实时翻译”导航入口。
  - 将文件整理为正常 UTF-8 中文标签，避免导航标签乱码。

## 行为说明

- 用户只需要选择两种语言，不需要选择单独的源语言和目标语言。
- 如果输入是语言 A，则输出语言 B。
- 如果输入是语言 B，则输出语言 A。
- 默认模型仍然来自工程 `.env` 配置。
- 用户选择的模型继续沿用模型选择页面中的配置。
