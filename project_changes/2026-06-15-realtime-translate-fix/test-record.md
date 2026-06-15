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

## 重点检查

- `front/vite.config.ts` 已加入 `/translate/` 代理。
- 翻译请求体已包含 `fast_mode: true`。
- 翻译 prompt 已包含禁止思考输出的中文规则。
- 页面布局为 `grid-cols-2`，始终左右双栏。
