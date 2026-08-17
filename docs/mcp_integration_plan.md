# MCP 接入与管理

MCP（Model Context Protocol）是 Doki 助手的外部 Tool 来源。本地 Tool 和 MCP Tool 最终都进入统一 ToolRegistry、Skill 解析和 GuardedTool，不存在两套 Agent 执行规则。

## 当前实现

```text
backend/app/config/mcp.example.yaml  # 仓库模板，默认禁用
backend/app/config/mcp.local.yaml    # 本机可写配置，Git 忽略
backend/app/agent/mcp/
  config.py       YAML 读取、server 更新、tool override 和删除
  provider.py     transport、tools/list、tools/call、连接错误
  adapter.py      MCP schema -> Pydantic schema -> LangChain BaseTool
  registry.py     discovery cache、refresh、ensure_fresh、catalog
backend/app/router/mcp_router.py
backend/app/agent/skill_registry.py
backend/app/agent/tool_guard.py
front/src/pages/ToolManager.tsx
```

当前支持：

- `stdio`、`sse`、`http` 和 `streamable_http` transport。
- server 级 enabled、allow/deny、默认风险、确认、超时和输出限制。
- tool 级 label、description、enabled、风险、确认、超时和输出限制 override。
- 启动 discovery、管理员 refresh 和错误态惰性自愈。
- ToolManager 展示本地 Tool、MCP server 和 MCP Tool。
- 管理员更新或删除 server/tool，配置写回 `mcp.local.yaml`。
- 普通登录用户只读，管理员执行修改操作。

当前没有独立的连接测试 API、数据库配置中心、secret store 或完整审计记录。

## 调用链路

```mermaid
flowchart TD
  Config[mcp.local.yaml] --> Provider[McpToolProvider]
  Provider --> List[MCP tools/list]
  List --> Registry[McpToolRegistry]
  Registry --> Adapter[LangChain adapter]
  Adapter --> Unified[ToolRegistry]
  Local[Local tools] --> Unified
  Unified --> Resolve[resolve_skills]
  Resolve --> Guard[GuardedTool]
  Guard --> Agent[AgentExecutor]
  Agent --> Call[MCP tools/call]
  Call --> Provider
  Guard --> Events[SSE and confirmation]
```

边界：

- provider 只负责 MCP 协议、连接和远程调用。
- registry 负责已发现工具的缓存和公开 catalog。
- adapter 负责参数 schema 和 LangChain Tool 适配。
- SkillRegistry 将本地 Tool 与 MCP Tool 合并。
- GuardedTool 负责执行预算、确认、超时和输出截断。

## 本地 Tool 与 MCP Tool

| 类型 | 来源 | 执行位置 | 典型用途 |
|------|------|----------|----------|
| 本地 Tool | `backend/app/agent/tools/<id>/` | FastAPI 进程 | 内部数据库、笔记、记忆、RAG |
| MCP Tool | `mcp.local.yaml` 指向的 server | 外部进程或服务 | 外部系统、跨语言工具、桌面或网络能力 |

进入 Agent 后两者都转换为 `ToolDefinition`，再包装为 GuardedTool。MCP Tool 的 `source` 为 `mcp`，并保留 `provider_id` 和 `external_name`，便于事件和待确认动作恢复真实来源。

## 配置文件

配置入口：

```text
backend/app/config/mcp.example.yaml
backend/app/config/mcp.local.yaml
```

读取顺序为 `MCP_CONFIG_PATH`、`mcp.local.yaml`、`mcp.example.yaml`。写操作始终使用显式路径或本机文件；若本机文件不存在，会先从示例创建。仓库示例中的 server 全部默认禁用。

server 字段：

| 字段 | 说明 |
|------|------|
| `id` | server 唯一 ID |
| `label` / `description` | UI 展示信息 |
| `enabled` | 是否参加 discovery |
| `transport` | `stdio`、`sse`、`http`、`streamable_http` |
| `command` / `args` / `env` | stdio 子进程配置 |
| `url` | SSE 或 streamable HTTP 地址 |
| `allow_tools` | 非空时只允许列出的外部工具名 |
| `deny_tools` | 显式拒绝的外部工具名 |
| `default_risk_level` | Tool 默认 `low/medium/high` |
| `default_requires_confirmation` | Tool 默认是否需要确认 |
| `timeout_seconds` | 默认单次执行超时 |
| `max_output_chars` | 默认输出截断长度 |
| `tool_overrides` | 针对外部工具名的覆盖 |

示例：

```yaml
servers:
  - id: example_stdio
    label: Example stdio server
    description: Read-only example
    enabled: true
    transport: stdio
    command: python
    args:
      - mcp_servers/example_server.py
    env: {}
    allow_tools:
      - lookup
    deny_tools: []
    default_risk_level: low
    default_requires_confirmation: false
    timeout_seconds: 10
    max_output_chars: 5000
    tool_overrides:
      lookup:
        label: Public lookup
        enabled: true
        risk_level: low
        requires_confirmation: false
        timeout_seconds: 8
        max_output_chars: 3000
```

默认值是保守的：未配置风险时为 `medium`，未配置确认时为 `true`。仓库示例包含两个开发/演示 server，但均为禁用状态；部署环境必须显式启用并逐项审查。

## Tool ID

内部 Tool ID 由 server ID 和 MCP 原始工具名规范化：

```text
mcp_<server_id>_<tool_name>
```

ID 转为小写，非字母数字字符替换为下划线，并限制为 64 个字符。LangChain Tool name 由 adapter 生成，管理 API 使用的是内部 Tool ID，不是 MCP 原始名称。

## Discovery 生命周期

### FastAPI 启动

`backend/main.py` 在 startup 中执行：

```text
mcp_tool_registry.refresh()
skill_registry.reload()
```

某个 server 失败不会阻止 FastAPI 启动；provider 记录 `last_error`，普通聊天仍可使用本地工具。

### 请求时自愈

`prepare_agent_run` 调用 `mcp_tool_registry.ensure_fresh()`。只有 registry 处于需要恢复的状态时才刷新，正常状态不会每轮执行 `tools/list`。

### 管理员刷新

```http
POST /api/mcp/servers/refresh
```

刷新完成后自动 reload SkillRegistry，让最新 MCP Tool 进入统一 catalog。

## 管理 API

所有读取接口要求登录；修改接口要求管理员。

| 方法 | 路径 | 权限 | 作用 |
|------|------|------|------|
| GET | `/api/mcp/servers` | 登录 | server 状态与 last_error |
| GET | `/api/mcp/tools` | 登录 | 已发现 MCP Tool |
| GET | `/api/mcp/permissions` | 登录 | 当前用户是否可管理 MCP |
| POST | `/api/mcp/servers/refresh` | 管理员 | 重新 discovery |
| PATCH | `/api/mcp/servers/{server_id}` | 管理员 | 更新 enabled、展示信息或 URL |
| DELETE | `/api/mcp/servers/{server_id}` | 管理员 | 从 YAML 删除 server |
| PATCH | `/api/mcp/tools/{tool_id}` | 管理员 | 写入 tool override |
| DELETE | `/api/mcp/tools/{tool_id}` | 管理员 | 加入 server deny_tools |

server 更新目前不支持通过 API 修改 stdio command、args、env 或 transport。这些字段仍需人工编辑 YAML。

删除 MCP Tool 的语义是把其外部名称加入 `deny_tools`，并移除对应 override；不会修改外部 MCP server。

## ToolManager

前端 `/tools` 页面：

- 将本地 Tool 与 MCP Tool 分组展示。
- 按 MCP server 展示工具。
- 普通用户只读 MCP 配置。
- 管理员可以更新 server enabled、label、description 和非 stdio URL。
- 管理员可以更新 MCP Tool 展示、enabled、风险、确认、超时和输出限制。
- 管理员可以从项目删除 server 或屏蔽 Tool。

UI 保存后会立即触发后端 refresh。配置写回 Git 忽略的 `mcp.local.yaml`，不会污染仓库模板。

## stdio 环境

stdio server 是 FastAPI 启动的独立子进程。配置中的：

```yaml
command: python
```

会按 FastAPI 进程的 PATH 查找 Python，不保证使用 `backend/.venv`。如果系统 Python 没有安装 `mcp`，discovery 会失败。

推荐方案：

- 从 `backend` 使用 `uv run uvicorn ...` 启动 FastAPI，并保证 PATH 解析正确。
- 或在本地配置中把 `command` 指向明确的 venv Python。
- 不要把只在某台机器存在的绝对路径提交到共享配置。
- 更可移植的长期方案是让配置支持命令模板或运行器引用。

## 测试 server

仓库包含：

```text
backend/mcp_servers/powershell_ls_server.py
backend/mcp_servers/public_info_server.py
```

前者提供有界的只读项目文件列表；后者提供公开信息查询和连通性检查。它们是开发/演示配置，不是生产安全背书。

手动刷新：

```powershell
cd backend
uv run python -c "import asyncio; from app.agent.mcp.registry import mcp_tool_registry; print([t.to_public_dict() for t in asyncio.run(mcp_tool_registry.refresh())])"
```

启动后读取状态：

```powershell
Invoke-RestMethod http://127.0.0.1:18000/api/mcp/servers -Headers @{Authorization="Bearer $token"}
```

当前没有专用 `test` endpoint。`refresh` 只能证明 server 可连接并完成 `tools/list`，不能证明每个 Tool 的真实调用成功。

## 风险和确认

MCP Tool 的最终风险配置按以下顺序确定：

1. tool override。
2. server default。
3. config loader 的保守默认值。

进入 Agent 后，GuardedTool 执行：

- 本轮调用次数检查。
- `requires_confirmation` 阻断。
- Redis pending action。
- 用户确认后的来源恢复。
- 单次执行超时。
- 输出截断。

文件系统写入、Shell、数据库写入、外部消息发送和付费 API 应默认 `requires_confirmation: true`。只读 annotation 只能作为风险判断信号，不能替代项目侧配置。

## 已知限制

- 配置是共享 YAML，不支持按用户或环境分层。
- API 修改配置没有审计表和回滚版本。
- stdio env 可能包含 secret，当前没有 secret manager。
- 没有独立 server/tool test API 和最近测试记录。
- 外部 server 的权限边界仍由部署者负责；MCP 协议本身不构成沙箱。
- 多实例 FastAPI 同时写 `mcp.local.yaml` 没有并发控制。

后续工作见 [全量重构开发计划的后端功能域阶段](./roadmap_next.md#r4-后端功能域模块化)。
