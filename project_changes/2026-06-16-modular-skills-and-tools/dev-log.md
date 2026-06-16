# 2026-06-16 Skill 与 Tool 模块化改造

## 背景

Agent 原始能力链路依赖固定 Prompt 和集中式工具列表。为了支持前端选择 Skill、后续注册外部工具，并保持默认链路不回退，本次将 Skill 和 Tool 都改造成可扫描的模块化结构。

## 本次完成

- 新增静态 Skill Registry，扫描 `backend/app/agent/skills/*/skill.yaml` 和 `SKILL.md`。
- 增加 5 个默认 Skill：系统上下文、知识库问答、笔记检索、笔记写入、复习回顾。
- 聊天请求支持 `skill_ids` 和 `tool_ids`，未传时默认启用全部默认 Skill，复刻初版工具链路。
- 前端聊天输入区增加 Skill 下拉选择，默认全开。
- 左侧导航增加 `Skill` 和 `工具库` 页面。
- Skill 页面支持查看、编辑、新增、删除 Skill，并绑定工具。
- Skill 和 Tool 新增时进入独立新建状态，不再被列表自动选中第一个项目打断。
- Skill 详情加载增加失效保护，避免旧请求晚返回后覆盖新建草稿。
- Skill 的绑定工具区域改为按分类展开的二级菜单，避免工具数量增加后撑开页面。
- Tool 从 `agent_tools.py` 集中式函数集合拆分为独立模块目录。
- Tool Registry 改为扫描 `backend/app/agent/tools/*/tool.yaml`、`TOOL.md`、`tool.py`。
- 工具库页面移除 Python symbol 选择，改为编辑工具展示信息和执行说明。

## 当前目录结构

```text
backend/app/agent/
  tool_context.py
  skill_registry.py
  skills/
    system_context/
      skill.yaml
      SKILL.md
  tools/
    rag_summary/
      tool.yaml
      TOOL.md
      tool.py
```

## 执行链路

```text
前端 Skill 下拉
  -> GET /api/skills/catalog
  -> Vite 转发 /skills/catalog
  -> SkillRegistry 扫描 skills/*
  -> ToolRegistry 扫描 tools/*
  -> 返回默认 Skill 和 Tool 列表

用户发送消息
  -> POST /chat/agent/query/stream
  -> resolve_skills(skill_ids, tool_ids)
  -> 拼接主 Prompt、AI 模式 Prompt、已启用 Skill 指令
  -> 注入已绑定 Tool 的 BaseTool 实例
  -> LangChain Agent 执行
```

## 默认兼容性

当前默认 5 个 Skill 会解析出原始 9 个工具：

- 知识库检索
- 当前时间
- 用户信息
- 笔记搜索
- 笔记统计
- 今日回顾
- 标记回顾
- 创建笔记
- 关联推荐

前端没有显式修改 Skill 选择时，请求不发送 `skill_ids/tool_ids`，后端走默认全量解析，保持初版行为。

## 后续建议

- 将工具新增从占位模块升级为模板选择，例如 HTTP 工具、MCP 工具、数据库查询工具。
- 给 Tool 增加启用状态、权限范围、超时和参数 Schema 配置。
- 将 Skill/Tool 配置持久化到数据库，并保留文件模块作为系统默认能力包。
- 在前端增加 Tool 调用日志和 Skill 解析预览。
