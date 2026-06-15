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
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,dom.iterable,es2022 --types vite/client src\pages\AIChat.tsx src\api\chat.ts src\api\endpoints.ts
```

结果：通过。

## 检查点

- `build_chat_system_prompt` 已存在。
- 默认模式只使用 `main_prompt`。
- 非默认模式组合 `main_prompt` 和对应模式 prompt。
- Agent 流式响应继续使用 `custom_system_prompt`。
