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
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,dom.iterable,es2022 --types vite/client src\pages\RealtimeTranslate.tsx src\api\translate.ts src\api\endpoints.ts
```

结果：通过。

## 检查点

- 页面有 `实时对话` 和 `整篇翻译` 两个模式。
- 实时对话模式按 Enter 即发。
- 实时对话模式每句话单独请求，支持多条同时翻译。
- 整篇翻译模式传 `fast_mode=false`。
- 实时对话模式传 `fast_mode=true`。
