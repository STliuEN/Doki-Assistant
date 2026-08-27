# Doki 助手前端

这是 Doki 助手的 React 单页应用。前端负责页面、交互状态、HTTP API 和 Agent SSE 消费；登录注册由 Django 用户服务提供，其他业务由 FastAPI 提供。

## 技术栈

- React 19。
- TypeScript 6。
- Vite 8。
- React Router 6。
- Zustand 5。
- Tailwind CSS 3。
- Tiptap 2。
- i18next。
- Vitest 4。

Vite 8 要求 Node.js `^20.19.0 || >=22.12.0`。Node.js 18 不受当前依赖支持。

前端完整使用 npm 管理依赖和脚本，`package-lock.json` 是受版本控制的锁文件；安装使用 `npm ci`，不需要 yarn 或 pnpm。

## 安装与运行

```powershell
cd front
npm ci
npm run dev -- --host 127.0.0.1 --port 18080
```

默认访问：<http://127.0.0.1:18080>

常用命令：

```powershell
npm run test
npm run build
npm run lint
npm run preview
```

## 后端依赖

开发服务器默认代理：

```text
FastAPI: http://127.0.0.1:18000
Django:  http://127.0.0.1:18001
```

覆盖目标：

```powershell
$env:VITE_BACKEND_TARGET='http://127.0.0.1:18000'
$env:VITE_USER_TARGET='http://127.0.0.1:18001'
npm run dev
```

代理规则位于 `vite.config.ts`：

- `/user`、`/file` -> Django。
- `/chat`、`/knowledge`、`/note`、`/memory`、`/model-config`、`/translate`、`/health` -> FastAPI。
- `/api/mcp` -> FastAPI，保留路径。
- `/api/skills`、`/api/tools` -> FastAPI，并移除 `/api` 前缀。

前端开发时 API 使用相对路径。生产环境必须自行提供等价的反向代理，仓库目前没有生产代理配置。

## 目录

```text
src/
  api/
    client.ts          Axios 实例、JWT header 和 401 处理
    endpoints.ts       共享 endpoint 常量
    auth.ts            认证 API
    chat.ts            Agent、Skill、Tool、MCP API
    knowledge.ts       知识库 API
    memory.ts          记忆中心 API
    modelConfig.ts     模型配置 API
    notes.ts           笔记 API
    noteTemplates.ts   笔记模板 API
    sessions.ts        会话 API
    translate.ts       翻译 API
  components/          通用、布局、知识库和笔记组件
  features/chat/
    hooks/useChatStream.ts
    storage.ts
    types.ts
    __tests__/
  hooks/               通用 hooks
  i18n/                中英文资源
  layouts/             MainLayout、AuthLayout
  pages/               页面组件
  router/              路由定义
  stores/              用户、会话、主题、语言状态
  types/               共享 API 类型
```

## 页面路由

| 路径 | 页面 |
|------|------|
| `/login` | 登录 |
| `/register` | 注册 |
| `/`、`/notes` | 笔记列表 |
| `/notes/new`、`/notes/:id` | 笔记编辑 |
| `/chat`、`/chat/:sessionId` | Agent 对话 |
| `/sessions` | 会话列表 |
| `/knowledge` | 知识库 |
| `/memory` | 记忆中心 |
| `/skills` | Skill 管理 |
| `/tools` | 本地 Tool 与 MCP 管理 |
| `/model-settings` | 用户模型配置 |
| `/translate` | 实时翻译 |
| `/profile` | 用户资料 |
| `/settings` | 主题和语言设置 |
| `/about` | 项目信息 |

页面使用 `React.lazy` 和 `Suspense` 延迟加载。

## 认证

`useUserStore` 是认证状态的唯一来源，由 Zustand persist 保存到：

```text
localStorage["user-store"]
```

持久化状态包含 access token、refresh token、用户资料和登录标志。旧 `localStorage.jwt_token` 只用于升级时的一次性兼容读取，并会在登录或退出时删除，不应再由新代码读写。

`src/api/client.ts` 为 Axios 请求添加：

```http
Authorization: Bearer <access token>
```

后端返回 `401` 时，client 使用 refresh token 刷新一次并重试原请求。并发 `401` 会合并为同一个刷新请求；成功后保存轮换后的 access/refresh token，失败或没有 refresh token 时完整清理认证状态并跳转 `/login`。

Agent 和知识库 SSE 使用原生 `fetch`，不经过 Axios 刷新 interceptor；`useSSE` 从同一 store 读取 access token，并在 `401` 时清理认证状态。退出请求同时发送 Bearer access token 和请求体中的 refresh token，以撤销当前 token 对。认证或撤销依赖不可用时后端可能返回 `503`，前端不能把它当作成功响应。

不要在前端保存模型 API key 明文。用户模型密钥由后端加密保存，前端只处理输入和脱敏结果。

## Agent SSE

主要实现：

```text
src/features/chat/hooks/useChatStream.ts
src/features/chat/types.ts
src/features/chat/__tests__/useChatStream.test.ts
```

支持的事件：

- `thinking`。
- `waiting_confirmation`。
- `response`。
- `error`。
- `done`。

所有事件都要求 `schema_version: "1.0"`；未知版本会中止当前流并显示错误。流处理会缓冲 response chunk，并在 thinking、确认、错误和完成事件前 flush，保证 UI 消息顺序与后端事件顺序一致。

`done.session_id` 用于新会话导航和状态同步。重新生成使用单独 endpoint，并覆盖已有 assistant 消息，而不是追加重复回答。

## 状态边界

- `useUserStore`：当前用户和认证相关状态。
- `useSessionStore`：当前会话状态。
- `useThemeStore`：主题并同步到 `<html class="dark">`。
- `useLanguageStore`：语言选择。
- 聊天流的临时 buffer 和 pending confirmation 由 feature hook 管理。

新增跨页面状态前先判断是否真的需要全局 store。请求期或组件期状态优先留在 feature/page 内。

## 测试

```powershell
npm run test
```

当前 Vitest 重点验证：

- access/refresh token 同库存储、刷新轮换、并发刷新合并和失败清理。
- Markdown 危险 URL 与原始 HTML 的安全渲染。
- SSE 分包和多事件解析。
- SSE schema version 校验。
- thinking/error 前的 response flush。
- regenerate 覆盖语义。
- `done.session_id` 传递。
- 高风险确认事件。

构建验证：

```powershell
npm run build
```

## 当前维护边界

- `AIChat.tsx` 已把 SSE hook、types 和 storage 拆到 `features/chat`，但设置、catalog 和消息 UI 仍需继续拆分。
- `NoteEditor.tsx`、`ToolManager.tsx` 和 `KnowledgeBase.tsx` 仍是大页面。
- 当前没有 E2E 浏览器测试。
- 当前没有生产静态资源和反向代理部署配置。

历史全项目运行说明见[归档开发说明](../docs/archive/2026-08-26/development_setup.md)；当前架构执行入口见[架构重写计划](../docs/architecture_rewrite_plan.md)。
