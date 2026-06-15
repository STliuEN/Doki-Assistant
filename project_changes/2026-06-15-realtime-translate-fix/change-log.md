# 修改记录

## 后端

- 更新 `backend/app/prompt/bidirectional_translate_prompt.txt`
  - 改为更短的中文实时翻译 prompt。
  - 明确禁止输出思考过程、推理说明、语言标签和标题。
- 更新 `backend/app/schemas/translate.py`
  - 新增 `fast_mode: bool = True`。
- 重写 `backend/app/services/translate_service.py`
  - 默认在快速模式下追加 `/no_think`。
  - 对输出做 `<think>...</think>` 和推理行清理。
  - 错误日志和 SSE 错误内容改为正常中文。
- 更新 `backend/app/router/translate.py`
  - 将 `fast_mode` 传入翻译服务。

## 前端

- 更新 `front/vite.config.ts`
  - 新增 `/translate/` 代理到 FastAPI 后端，修复翻译请求不启动的问题。
- 重写 `front/src/pages/RealtimeTranslate.tsx`
  - 修复中文乱码。
  - 请求体增加 `fast_mode: true`。
  - 页面始终保持左右双栏，不再按宽度切换成上下布局。
  - 文案强调快速模式不输出思考。

## 影响

- 使用小模型时更适合实时翻译。
- 对 Qwen 这类可能输出思考过程的模型更稳。
- 开发环境下 `/translate/dialogue/stream` 可以被 Vite 正确代理到后端。
