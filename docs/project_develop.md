# 项目发展与当前架构

本文记录项目从基础 RAG 到个人 Agent 平台的演进，并按当前代码说明真实运行链路。

## 演进阶段

### 阶段一：基础 RAG 服务

最早版本是 FastAPI + LangChain + ChromaDB 的 RAG 演示：

```text
文档上传 -> 文档切片 -> 向量化 -> 检索 -> LLM 生成
```

这条基础链路保留在 `base-rag` 分支，适合学习最小 RAG 服务。

### 阶段二：RAG NoteBook

项目随后围绕“笔记写了以后如何再利用”扩展：

- Markdown 笔记管理
- LLM 自动标签
- 语义搜索
- 笔记与知识库关联推荐
- 复习/回顾
- AI 写作辅助

这一阶段的核心变化是：RAG 不再只服务上传文档问答，也开始成为笔记搜索、关联推荐和写作辅助的知识底座。

### 阶段三：多功能 Agent 平台

当前 `master` 已经转向个人 Agent 工作台：

- 多模型配置与选择
- AI 对话模式
- Skill/Tool 注册和前端选择
- 记忆中心
- 知识库 RAG
- 笔记系统
- 实时翻译
- 会话持久化

当前定位不是“单一笔记应用”，而是“以 RAG、记忆和工具调用为核心的个人 Agent 平台”。

## 当前系统架构

```text
React 前端
  -> FastAPI 后端
    -> LangChain AgentExecutor
    -> Skill Registry / Tool Registry
    -> RAG / Note / Memory / Translate 服务
    -> MySQL / Redis / ChromaDB
  -> Django 用户服务
```

主要组件：

- `front/src/pages/AIChat.tsx`：对话页，负责模型、AI 模式、Skill、策略菜单、消息刷新和删除。
- `backend/app/router/chat.py`：Agent 对话入口、prompt 拼接、skill 预路由和 SSE 返回。
- `backend/app/agent/agent.py`：创建 LangChain tool calling Agent，执行工具并推送 thinking。
- `backend/app/agent/skill_registry.py`：扫描 Skill/Tool 文件模块。
- `backend/app/agent/intent_router.py`：从用户已选 Skill 中做本轮预路由。
- `backend/app/services/database_session_manager.py`：会话、消息、上下文裁剪、刷新覆盖和删除。
- `backend/app/rag/rag_service.py`：RAG 检索、笔记召回、摘要生成和动态检索数量。
- `backend/app/router/memory_router.py`：记忆中心 API。

## Prompt 拼接方式

当前 prompt 拼接在 `backend/app/router/chat.py#build_chat_system_prompt` 中完成。

拼接顺序：

```text
1. main_prompt
2. 当前启用 Skill 的 SKILL.md 内容
3. 本次可用工具名称列表
4. 当前 AI 模式 prompt（非 main_prompt 时追加）
```

对应逻辑：

```text
load_prompt("main_prompt")
  + "## 当前启用 Skills"
  + skill_prompts
  + "请只依赖当前已启用 skill..."
  + "## 本次可用工具"
  + tool_names
  + mode prompt
```

注意：

- `TOOL.md` 不直接拼进 `system_prompt`，而是覆盖 LangChain tool description，让模型在 tool calling schema 中看到工具说明。
- 用户未手动选择 Skill 时，后端使用 registry 中的默认 Skill。
- 用户手动选择 Skill 后，后端只在这些 Skill 内做预路由，不会自动引入未选择能力。
- 如果请求显式传 `tool_ids`，会按精确工具控制跳过 skill 预路由。

## Agent 执行流程

```text
前端发送消息
  -> POST /chat/agent/query/stream
  -> JWT 鉴权得到 user_id
  -> 读取模型配置
  -> 确认 prompt_type
  -> 解析候选 Skill
  -> intent_router 预路由
  -> resolve_skills 得到 Skill prompt 和 Tool 实例
  -> build_chat_system_prompt
  -> get_agent_stream_response
  -> get_context 裁剪历史
  -> create_tool_calling_agent
  -> AgentExecutor.astream
  -> thinking / response / done SSE
  -> 保存 user + assistant 消息
```

当前回答流式方式：

- thinking 事件会在 Agent 执行时实时推送。
- 普通工具调用会通过 `intermediate_steps` 形成 thinking 文本。
- RAG 工具内部还会主动推送更细的检索 thinking。
- 最终回答当前仍是 Agent 完整结束后再按 chunk 发送，不是模型 token 级流式。

## 上下文策略

前端 `策略` 二级菜单包含：

- 上下文长度：`Auto / 低 / 中 / 高 / 自定义 / 仅当前`
- RAG 检索：`Auto / 低 / 中 / 高 / 自定义`

后端上下文裁剪在 `DatabaseSessionManager.trim_history`：

- `current_only`：不带历史。
- `custom`：按最近对话轮数保留。
- `low/medium/high/auto`：按粗略 token 预算保留历史。
- Auto 默认 token 预算为 4000。

当前仍是“裁剪”，不是“自动摘要压缩”。自动摘要见 roadmap P1。

## RAG 动态检索

前端会随对话请求发送：

```json
{
  "rag_retrieval": {
    "mode": "auto",
    "knowledge_k": 6,
    "note_k": 3,
    "summary_k": 3
  }
}
```

后端通过 tool context 传入 `RagService`：

```text
chat.py
  -> agent.py set_rag_retrieval_settings
  -> rag_summary_tool
  -> RagService(retrieval_settings=...)
```

当前预设：

- low：知识库 4，笔记 2，摘要 2
- medium：知识库 6，笔记 3，摘要 3
- high：知识库 10，笔记 5，摘要 5
- custom：知识库最多 20，笔记最多 20，摘要最多 8
- auto：根据问题长度和“总结/对比/分析/全部/详细/综合”等词选择 low/medium/high

## 记忆中心状态

记忆中心已经不是计划稿，而是当前主功能之一：

- 后端模型：`MemoryItem`
- 后端服务：`memory_service`
- 后端路由：`/memory/*`
- 前端页面：`MemoryCenter`
- Agent 工具：create/list/get/update/delete/complete/postpone/archive/reviewed 等
- Skill：memory read/write/cleanup 相关 Skill

记忆类型：

- `review`
- `todo`
- `reminder`
- `long_term`
- `memo`

下一步重点是主动提醒、从对话自动提炼事项、语义搜索和高风险操作确认。

## 权限与安全现状

已有：

- JWT Bearer 鉴权。
- 多数业务路由按当前 `user_id` 隔离。
- 前端 HTTP/SSE 自动带 token。
- 删除会话、消息、记忆、模型配置、Skill/Tool 等操作有前端确认。

不足：

- 没有角色或管理员权限模型。
- `skill_router`、`tool_router` 当前缺少后端鉴权。
- `/chat/sessions` 和 `/chat/reorder` 需要补齐鉴权。
- Agent 工具没有统一风险等级和二次确认。
- 高风险操作不能只依赖 prompt 约束。

这些被列为下一阶段 P0。

## 后续方向

详细计划见 [下一阶段开发计划](./roadmap_next.md)。当前推荐顺序：

1. 补齐权限和高风险工具确认。
2. thinking 事件结构化、计时和工具可观察性。
3. 长任务预算和停止。
4. 上下文自动摘要压缩。
5. 记忆中心主动提醒和事项提炼。
6. MCP 外部工具接入。
7. 字幕/会议翻译。
8. 桌面端验证。

