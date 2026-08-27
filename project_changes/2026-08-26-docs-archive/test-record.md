# 2026-08-26 docs 一级目录归档验证记录

状态：待验证

## 环境限制

- Windows PowerShell；当前工作树 `C:\\codes_projects\\Doki-Assistant-main`。
- 本批只执行文件归档和 Markdown 链接检查，不连接真实服务或修改业务数据。

## 证据表

| ID | 命令 | 阈值 | 实际结果 | 状态 |
|---|---|---|---|---|
| DOC-ROOT-SCOPE | `Get-ChildItem docs -File` | 只含 README、主计划、蓝图、阶段模板 | 4 个文件：`README.md`、`architecture_rewrite_plan.md`、`architecture-target-blueprint-2026-08-26.md`、`stage-execution-record-template-2026-08-26.md` | verified-local |
| DOC-ARCHIVE-COUNT | `Get-ChildItem docs/archive/2026-08-26 -File` | 18 个旧/专项文档加归档 README | 18 个历史文档，另有 `README.md` 归档索引 | verified-local |
| DOC-LINKS | `powershell -ExecutionPolicy Bypass -File scripts/check-docs.ps1` | 零断链 | `Markdown checks passed: 163 files, 122 local links` | verified-local |
| DOC-WHITESPACE | `git diff --check` | 零空白错误 | passed | verified-local |
| DOC-DATA-SCOPE | `git status --short --untracked-files=all` | 无业务代码/数据改动 | 仅文档移动、链接更新和本批记录 | verified-local |

## 不能证明的内容

本检查不证明归档文档中的历史架构仍适用于当前系统，也不证明 AR-0、Skill、RAG、认证迁移或恢复门禁已经完成。
