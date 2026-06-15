# 修改记录

## 后端

- 更新 `backend/app/prompt/bidirectional_translate_prompt.txt`
  - 增加 `{mode_instruction}`。
  - 整篇翻译模式允许必要的内部思考。
  - 实时对话模式禁止输出思考和推理说明。
- 更新 `backend/app/services/translate_service.py`
  - `fast_mode=true` 时继续追加 `/no_think`。
  - `fast_mode=false` 时不追加 `/no_think`。

## 前端

- 重写 `front/src/pages/RealtimeTranslate.tsx`
  - 增加 `实时对话` 和 `整篇翻译` 两个模式。
  - 移除顶部说明文字，只保留功能控件。
  - 整篇翻译模式保留左右大框和手动开始按钮。
  - 实时对话模式支持 Enter 发送，Shift+Enter 换行。
  - 实时对话模式每句话独立发起 SSE 请求，不等待上一句结束。
  - 右侧逐句显示译文，每条翻译有独立运行状态。
  - 复制和保存笔记兼容两个模式。

## 行为

- 实时对话：高响应、禁思考、逐句并发。
- 整篇翻译：手动启动、允许内部思考、保持整段上下文。
