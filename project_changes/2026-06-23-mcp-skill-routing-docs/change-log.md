# 2026-06-23 MCP 接入与 Skill 路由文档同步

## 背景

本次整理基于当前 `ai_document_assistant` 分支的 MCP 接入结果，以及运行时排查中发现的两个容易误判的问题：

- MCP smoke test 已通过 `mcp.yaml` 接入到统一 Skill/Tool 体系。
- 聊天页可以同时启用多个 Skill，但后端会按当前输入做意图路由，可能把本轮可用 Skill 收窄到 MCP 连通性测试。
- stdio MCP server 由子进程启动，子进程使用的 Python 环境必须能 import `mcp` 包。

## 文档更新

- 更新 `docs/mcp_integration_plan.md`：
  - 补充多 Skill 启用方式：多个 Skill 会合并为同一个 Agent 的可用工具集，而不是启动多个 Agent 并行执行。
  - 记录 `route_skills` 的收窄行为：命中 MCP 连通性测试意图时，可能只保留 `mcp_smoke_test`。
  - 补充聊天页 `localStorage` 中 `ai_chat_skill_ids` 对当前 Skill 选择的影响。
  - 补充默认 PowerShell LS smoke server 的验证命令和运行边界。
  - 记录 stdio 子进程需要使用正确 Python 环境的注意事项。
- 更新 `docs/development_setup.md`：
  - 补充 MCP stdio server 的启动环境说明。
  - 明确推荐用 `uv run` 验证 MCP 发现链路。
- 更新 `docs/troubleshooting.md`：
  - 新增“聊天页只剩 MCP Skill 或其他 Skill 没被调用”的排查项。
  - 新增“MCP stdio server 子进程找不到 `mcp` 包”的排查项。
- 同步调整工具输出默认字符上限：
  - 本地 Tool、MCP Tool、ToolManager 表单和默认 MCP smoke 配置的 `max_output_chars` 从 4000 扩展到 10000。
  - 保留 `agent.yaml` 的 `max_output_chars_per_tool: 16000`，该项用于 SSE 工具事件预览，不是单个工具定义的默认截断值。

## 当前运行结论

- 后端默认 Skill 列表仍包含系统上下文、知识库、笔记、记忆、复习和 MCP smoke test。
- 如果前端当前只勾选了 `mcp_smoke_test`，请求体会只发送该 Skill。
- 如果用户输入包含 `mcp`、连通测试、smoke test 等关键词，后端规则路由会把本轮 Skill 收窄到 `mcp_smoke_test`。
- 显式传入 `tool_ids` 时，后端会跳过 Skill 预路由，按传入工具精确控制。

## 新增 Public Info MCP Skill

- 新增 `backend/mcp_servers/public_info_server.py`。
- 新增 MCP server 配置 `public_info_lookup`，包含两个只读外部查询工具：
  - `query_university_info`：调用 `https://api.52vmy.cn/api/query/daxue` 查询中国大学公开信息。
  - `ping_check`：调用 `https://test.harumoe.cn/api/other/ping` 做公共域名或公网 IP 的 PING/端口检测。
- 新增 Skill `backend/app/agent/skills/public_info_lookup/`：
  - `skill.yaml` 绑定 `mcp_public_info_lookup_query_university_info` 和 `mcp_public_info_lookup_ping_check`。
  - `SKILL.md` 约束使用场景、参数填写、内网/本机地址禁止检测和外部信息可信度说明。
- 该 Skill 设置为 `default: false`，避免普通聊天自动触发外部请求。
- `ping_check` 增加基础 SSRF 防护：拒绝 localhost、内网 IP、链路本地地址、保留地址、多播地址和明显 URL/命令形态输入。

## 验证记录

- 已执行后端语法检查：
  ```powershell
  python -m compileall -q backend\app backend\mcp_servers
  ```
- 已用 `uv run` 验证 MCP 发现链路可发现默认 smoke tool：
  ```powershell
  cd backend
  uv run python -c "import asyncio; from app.agent.mcp.registry import mcp_tool_registry; print([t.to_public_dict() for t in asyncio.run(mcp_tool_registry.refresh())])"
  ```
- 已验证 `public_info_lookup` 能被 MCP 发现并装配到 Skill：
  - `mcp_public_info_lookup_query_university_info`
  - `mcp_public_info_lookup_ping_check`
- 已联网验证 `query_university_info` 查询 `武汉大学` 成功返回公开信息。
- 已验证 `test.harumoe.cn` PING API 在当前网络环境中直接访问会连接失败；MCP 包装层可以正常发起调用，但外部端点当前不可达。
- 普通 `python` 启动 stdio 子进程时曾出现子进程找不到 `mcp` 包，原因是 `mcp.yaml` 中 `command: python` 依赖当前 PATH/虚拟环境。
- 前端构建未完成验证：当前 shell 中 `npm` 命令不可用。

## 后续建议

- 如果 `mcp_smoke_test` 仅用于调试，建议将 `backend/app/agent/skills/mcp_smoke_test/skill.yaml` 的 `default` 改为 `false`，避免日常对话默认携带 MCP 测试能力。
- 在聊天页增加“恢复默认 Skill”按钮，清理或重置 `ai_chat_skill_ids`。
- 在 MCP provider 调用层补充 allow/deny、tool enabled、available 的二次校验，避免非 Agent 装配路径绕过工具级治理。
- 为 MCP refresh/test 增加前端操作入口和结构化错误提示。
