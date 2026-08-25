---
name: mcp-smoke-test
description: "专门用于验证 MCP 外部工具发现、调用和返回是否正常。"
---
# MCP 连通性测试

用于验证 MCP 外部工具是否已经被后端发现、注册并可以被 Agent 调用。

- 只用于低风险 smoke test，不用于日常文件管理。
- 当用户要求测试 MCP、检查 MCP 是否能调用、或列一下项目目录确认连通性时，调用 `mcp_powershell_ls_test_list_project_files_tool`。
- 默认列项目根目录，`relative_path` 使用 `"."`，`limit` 使用 10 到 30 之间的值。
- 不要请求任意 PowerShell 命令，不要尝试写入、删除、递归扫描或访问项目目录之外的路径。
- 工具返回 JSON 文件列表后，用简短中文总结：说明 MCP 调用成功、列出了哪些顶层条目，以及是否有错误。
