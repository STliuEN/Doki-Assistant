# 测试记录

## 后端编译

命令：

```powershell
cd backend
uv run python -m compileall app
```

结果：通过。

## 前端局部 TypeScript 检查

命令：

```powershell
cd front
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,dom.iterable,es2022 --types vite/client src\pages\AIChat.tsx src\pages\RealtimeTranslate.tsx src\api\chat.ts src\api\translate.ts src\api\endpoints.ts
```

结果：通过。

## 检查点

- `GET /chat/prompt-modes` 已存在。
- AI 对话请求会携带 `prompt_type`。
- Agent 流式执行会使用传入的 `custom_system_prompt`。
- AI 对话模型选择写入 `localStorage`。
- AI 对话模式选择写入 `localStorage`。
- 实时翻译模型选择写入 `localStorage`。
