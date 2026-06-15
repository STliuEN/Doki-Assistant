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
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,dom.iterable,es2022 --types vite/client src\pages\RealtimeTranslate.tsx src\components\layout\Sidebar.tsx src\api\translate.ts src\api\endpoints.ts
```

结果：通过。

## 前端全量 TypeScript 检查

命令：

```powershell
cd front
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,dom.iterable,es2022 --types vite/client src\pages\RealtimeTranslate.tsx src\components\layout\Sidebar.tsx src\api\translate.ts src\router\index.tsx src\api\endpoints.ts
```

结果：未通过。

原因：检查会递归进入现有 `NoteEditor.tsx` 和 `NoteList.tsx`，其中存在与本次修改无关的旧 TypeScript 错误，例如 `setTemplates`、`editForm`、`templateItems`、`saveStatus` 等未定义。

结论：本次新增和直接修改的前端文件通过局部检查；全量前端检查仍受既有笔记页面问题影响。
