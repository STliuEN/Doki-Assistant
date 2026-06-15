# README Architecture Update Test Record

## Basic Checks

Command:

```powershell
rg -n "## 项目架构|Clean OpenAI-Compatible Caller|ModelSettings.tsx|clean_openai_chat.py|用户模型配置" README.md
```

Result:

- Passed.

Command:

```powershell
git diff --check -- README.md project_changes/2026-06-15-readme-architecture-update/plan.md project_changes/2026-06-15-readme-architecture-update/change-log.md project_changes/2026-06-15-readme-architecture-update/test-record.md
```

Result:

- Passed.
