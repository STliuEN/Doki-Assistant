# 修改记录

## 后端

- 更新 `backend/app/schemas/translate.py`
  - 新增 `custom_instruction: str | None = None`。
- 更新 `backend/app/services/translate_service.py`
  - `_format_prompt` 支持 `custom_instruction`。
  - 非空时在 prompt 前注入：`用户额外翻译要求：...`。
- 更新 `backend/app/router/translate.py`
  - 将请求中的 `custom_instruction` 传入翻译服务。

## 前端

- 更新 `front/src/api/translate.ts`
  - 请求类型增加 `custom_instruction` 和 `fast_mode`。
- 更新 `front/src/pages/RealtimeTranslate.tsx`
  - 顶部模型选择右侧新增输入框。
  - 输入框默认空。
  - 整篇翻译和实时对话模式都会携带非空的额外要求。

## 行为

- 不填写额外要求时，翻译逻辑保持不变。
- 填写后，只影响当前页面发出的翻译请求。
- 额外要求不会替代双语互译规则，只作为语气、风格、措辞的辅助提示。
