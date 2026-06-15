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

- 后端 schema 已支持 `custom_instruction`。
- prompt 注入逻辑已添加。
- 前端顶部新增额外要求输入框。
- 请求体仅在输入框非空时携带 `custom_instruction`。
