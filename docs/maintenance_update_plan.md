# 仓库更新完整性整改计划

状态：待实施  
基线日期：2026-07-10  
适用范围：当前 `ai_document_assistant` 分支

本文处理依赖、生成文件、配置、安全、前端质量门禁和 CI 的更新完整性问题。产品功能路线仍以 [下一阶段路线图](./roadmap_next.md) 为准。

## 目标

完成后，仓库应满足：

- `pyproject.toml`、`uv.lock` 和兼容用 `requirements.txt` 不再产生不同 Python 环境。
- 跟踪中的 FastAPI OpenAPI 与当前路由、schema 完全一致。
- 示例配置不默认开启外部追踪，不使用可预测加密回退，也不提交个人管理员身份。
- 本机 MCP、安全配置与仓库模板分离。
- `npm run lint` 恢复为可执行的绿色质量门禁。
- Django 和 FastAPI 的 uv 配置可以在干净环境稳定复现。
- CI 自动阻止上述问题再次进入主分支。

## 已确认基线

| 检查项 | 当前结果 |
|--------|----------|
| Backend `uv lock --check` | 通过 |
| Django `uv lock --check` | 通过 |
| Backend tests | 45 passed，1 个 Pydantic 弃用警告 |
| Frontend Vitest | 4 passed |
| Offline smoke benchmark | 4/4 passed，得分均为 1.0 |
| Frontend clean-output build | 通过 |
| Frontend lint | 失败：41 errors、8 warnings |
| Backend requirements vs lock | 55 个版本不一致 |
| Django requirements vs lock | 一致 |
| Static OpenAPI vs current app | 23 paths vs 91 paths |
| Django system check | 代码通过；`uv run` 受本机 cache ACL 影响 |

## 范围边界

本计划包含：

- 依赖生成物和 OpenAPI 同步。
- 环境变量与本机配置边界。
- 前端 lint 恢复。
- uv、Pydantic 和索引配置整理。
- 自动校验脚本和 CI。

本计划不包含：

- 新产品功能。
- 数据库 Alembic migration 的完整实施。
- Agent、RAG 或前端页面的大规模重构。
- MCP 配置数据库化和完整审计系统。
- 生产部署基础设施。

这些事项继续保留在 [下一阶段路线图](./roadmap_next.md)。

## 实施顺序

```text
M0 baseline
  -> M1 dependency artifacts
  -> M2 OpenAPI artifact
  -> M3 security and local config
  -> M4 frontend lint
  -> M5 Python tooling cleanup
  -> M6 CI and drift prevention
```

M1、M2 可并行开发，但应在 M3 之前合入，先恢复仓库事实来源。M6 最后接入，使用前面各阶段已经稳定的命令。

## M0 固化基线

### 工作

- 保留当前后端、前端和 Benchmark 通过结果。
- 为整改建立独立分支或连续小提交。
- 记录当前用户模型配置是否包含已加密 API key。
- 记录本机 `SECRET_KEY`，只用于迁移判断，不写入日志或提交。
- 备份本机 `.env`、`mcp.yaml` 自定义项和管理员配置。

### 验收

```powershell
cd backend
uv run pytest -p no:cacheprovider
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9

cd ..\front
npm run test
npm run build -- --outDir dist-build-check
```

临时构建和 Benchmark 结果不得进入提交。

## M1 统一 Python 依赖生成物

### 当前问题

`backend/requirements.txt` 与 `backend/uv.lock` 有 55 个版本不一致，包括：

| Package | requirements | uv.lock |
|---------|--------------|---------|
| sentence-transformers | 5.5.0 | 5.5.1 |
| torch | 2.12.1+cu132 | 2.12.0+cu132 |
| transformers | 5.8.1 | 5.12.1 |

`uv.lock` 已通过 `uv lock --check`，因此本阶段以 `pyproject.toml + uv.lock` 为规范来源。

### 推荐方案

保留 `requirements.txt` 作为兼容导出文件，但禁止人工编辑。

### 工作

1. 确认 `requirements.txt` 的使用者和目标平台。
2. 从当前 `pyproject.toml` 重新生成 runtime requirements。
3. 不把 `dev` extra 混入 runtime requirements。
4. 增加只读一致性检查：临时生成后与跟踪文件比较。
5. Django 使用相同流程，即使当前没有漂移。
6. 在文件顶部或文档中明确“generated, do not edit”。

建议命令：

```powershell
cd backend
uv lock --check
uv pip compile pyproject.toml -o requirements.txt

cd ..\DjangoUserService
uv lock --check
uv pip compile pyproject.toml -o requirements.txt
```

实施时必须确认 torch 仍从 `pytorch-cu132` index 解析，不能让通用 PyPI wheel 替换 CUDA wheel。

### 涉及文件

- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/requirements.txt`
- `DjangoUserService/pyproject.toml`
- `DjangoUserService/uv.lock`
- `DjangoUserService/requirements.txt`
- 可选：`scripts/check-generated-dependencies.ps1`

### 完成标准

- 两个 `uv lock --check` 通过。
- requirements 中每个精确 pin 都与对应 lock 版本一致。
- `uv sync --extra dev` 后后端 45 项测试通过。
- Django `manage.py check` 通过。
- 临时生成 requirements 后 `git diff --exit-code` 无差异。

## M2 管理 FastAPI OpenAPI

### 当前问题

跟踪中的 `backend/openapi.json` 只有 23 条路径，当前应用动态生成 91 条路径。静态文件缺少 MCP、Memory、模型配置、Skill/Tool、重新生成等接口。

### 推荐方案

继续跟踪静态 OpenAPI，但将它定义为自动生成文件，并在 CI 检查一致性。若仓库没有客户端生成或外部发布需求，则可改为删除静态文件，只使用 `/openapi.json`；该决策应在实施前确认。

### 工作

1. 新增无网络、无数据库启动的导出脚本。
2. 脚本只 import FastAPI app 并调用 `app.openapi()`，不执行 startup event。
3. 使用稳定 JSON 格式：UTF-8、固定缩进、稳定 key 顺序和结尾换行。
4. 增加 `--check` 或临时输出比较模式。
5. 在路由/schema 变更清单中加入 OpenAPI 更新。

建议入口：

```text
backend/scripts/export_openapi.py
scripts/check-openapi.ps1
```

### 风险

- import `main` 会加载 registry 和部分模块；导出脚本必须避免触发真实模型、MCP discovery 和数据库连接。
- OpenAPI 中的 operation/schema 顺序必须稳定，否则 CI 会产生无意义 diff。

### 完成标准

- 静态与动态 OpenAPI path 集合一致。
- component schema 数量和内容一致。
- 连续运行两次导出不会产生 diff。
- CI 中 OpenAPI 漂移返回非零退出码。

## M3 收敛安全与本机配置

### M3.1 模型密钥加密键

当前加密逻辑：

```text
MODEL_CONFIG_ENCRYPTION_KEY
  -> SECRET_KEY
  -> dev-model-config-key
```

固定 dev key 不应成为运行时回退。

#### 迁移顺序

1. 首次加入 `MODEL_CONFIG_ENCRYPTION_KEY` 时，将它设置为当前 `SECRET_KEY` 的相同值。
2. 验证所有已保存模型 API key 仍可解密和连接。
3. 实现显式 re-encrypt 命令：旧 key 解密，新 key 加密。
4. 备份数据库后执行 re-encrypt。
5. 验证后再把 encryption key 与 JWT secret 分离。
6. 最后删除固定 `dev-model-config-key` 回退，并在缺失时启动失败。

直接设置全新的 encryption key 会让现有密文解密为空，不能跳过 re-encrypt。

### M3.2 示例环境变量

更新 `backend/.env.example`：

- 新增 `MODEL_CONFIG_ENCRYPTION_KEY`。
- 新增可选 `ADMIN_USER_IDS`、`ADMIN_USERNAMES`。
- `LANGCHAIN_TRACING_V2` 默认改为 `false`。
- secret 示例改为明确的 required placeholder。
- 区分当前变量和兼容别名。

代码读取但模板未列出的兼容变量：

- `ALIYUN_MODEL_NAME`
- `OLLAMA_CHAT_MODEL_NAME`
- `CHAT_API_KEY`

对每个兼容变量做决定：保留并标记 deprecated，或删除旧读取路径。不要同时保留多套无说明变量。

### M3.3 管理员配置

当前 `security.yaml` 提交了具体 UUID 和用户名。推荐改为：

```text
security.example.yaml   tracked
security.local.yaml     ignored
```

或仅使用 `ADMIN_USER_IDS/ADMIN_USERNAMES`。代码需支持 `SECURITY_CONFIG_PATH` 或 local override，并在没有管理员时给出明确诊断。

### M3.4 MCP 配置

当前 `mcp.yaml` 默认启用开发 server，且 ToolManager 会直接写回跟踪文件。推荐改为：

```text
mcp.example.yaml   tracked
mcp.local.yaml     ignored and writable
```

代码需支持 `MCP_CONFIG_PATH`，首次开发可从 example 复制。默认 server 应 disabled；启用外部网络或本地进程必须是显式操作。

### 完成标准

- 空 secret 或示例 secret 会阻止非开发环境启动。
- 已保存模型 key 在迁移前后均可解密。
- 默认复制 `.env.example` 不会开启 LangSmith tracing。
- Git 不再跟踪个人管理员身份或本机 MCP 修改。
- 普通用户、管理员和 MCP 权限测试通过。

## M4 恢复前端 lint gate

### 当前问题

当前结果：41 errors、8 warnings，集中在：

| Rule | Count | 处理方向 |
|------|-------|----------|
| `react-hooks/set-state-in-effect` | 20 | 调整数据加载和派生状态 |
| `react-refresh/only-export-components` | 16 | 对 router 文件做合理 override 或拆分 |
| `react-hooks/exhaustive-deps` | 8 | 修复 callback 稳定性和依赖数组 |
| `react-hooks/refs` | 3 | 禁止 render 阶段写 ref |
| `react-hooks/immutability` | 2 | 调整函数声明顺序或 useCallback |

### 分批处理

#### M4.1 先修正确性问题

- `TiptapEditor.tsx`、`NoteEditor.tsx`：把 render 阶段 ref 写入移到 effect 或使用稳定事件回调。
- `KnowledgeBase.tsx`、`NoteEditor.tsx`：修复声明前访问函数和潜在 stale closure。
- 修复所有 `exhaustive-deps`，必要时使用 `useCallback`；不能简单批量 disable。

#### M4.2 再处理 effect 派生状态

- 能从 props/state 直接计算的值改为 `useMemo` 或渲染期派生。
- 数据加载 effect 把 loading 设置和异步调用封装成稳定 callback。
- 需要在 key 变化时重置内部状态的组件，优先考虑 `key` 或 reducer，而不是同步 effect 链。
- 每次改动都运行相关页面测试，防止出现重复请求和状态闪烁。

#### M4.3 收敛 Fast Refresh 规则

`router/index.tsx` 是路由配置，不是组件模块。优先方案：

- 把 LazyLoad 组件移到独立文件；或
- 对明确的 route configuration 文件设置窄范围 override。

不要全局关闭 `only-export-components`。

### 完成标准

```powershell
cd front
npm run lint
npm run test
npm run build -- --outDir dist-build-check
```

- lint 0 error、0 warning。
- Vitest 4 项保持通过并补充受影响组件测试。
- 构建通过。
- 网络请求次数和页面初始化行为没有回归。

## M5 Python 工具链清理

### M5.1 Django uv cache ACL

现状：现有 venv 直接运行 `manage.py check` 通过，但 `uv run` 可能因 `.uv-cache/sdists-v9/.git` 拒绝访问失败。

处理：

1. 关闭占用 Django `.venv` 和 `.uv-cache` 的进程。
2. 检查 `.uv-cache/sdists-v9/.git` 的来源、ACL 和只读属性。
3. 只删除确认属于缓存的损坏条目，不删除项目 `.git`。
4. 重新执行 `uv sync` 和 `uv run python manage.py check`。

### M5.2 统一 Django package index

`DjangoUserService/pyproject.toml` 同时声明清华 index 和 PyPI `index-url`。选择一个默认源，并明确 fallback；避免不同 uv 版本使用不同优先级。

### M5.3 Pydantic V3 准备

把 `failed_response.py` 中内部 `class Config` 改为 `SettingsConfigDict`，消除当前弃用警告，并增加 Settings 加载测试。

### M5.4 开发工具可用性

确认 `uv sync --extra dev` 后以下命令可用：

```powershell
uv run pytest
uv run ruff check app tests
```

若保留 black/isort/ruff，CI 必须实际运行；否则从 dev extra 移除未采用工具，避免虚假的工具链声明。

### 完成标准

- Django `uv run python manage.py check` 通过。
- index 配置只有一个明确默认来源。
- 后端测试无 Pydantic Config 弃用警告。
- ruff 命令在干净 dev 环境可运行。

## M6 自动化防漂移

### 推荐 CI jobs

当前 backend lock 限定 Windows，初始 CI 使用 Windows runner：

1. `docs-check`
   - Markdown 本地链接。
   - Markdown anchor。
   - 代码围栏。
   - 已删除路径和关键版本事实扫描。
2. `backend-test`
   - `uv lock --check`。
   - requirements 一致性。
   - pytest。
   - ruff。
   - smoke benchmark。
3. `django-check`
   - `uv lock --check`。
   - requirements 一致性。
   - `manage.py check`。
4. `frontend`
   - Node 22。
   - `npm ci`。
   - lint、test、build。
5. `generated-artifacts`
   - OpenAPI check。
   - requirements check。

### CI 约束

- Offline smoke 不得访问真实 MySQL、Embedding、MCP 或用户数据。
- 不在 CI 注入生产 API key。
- LangSmith tracing 默认关闭。
- 生成文件检查使用临时目录并在结束后清理。
- 缓存 key 必须包含 lock 文件 hash。

### 可选 pre-commit

本地 pre-commit 只运行快速检查：

- Markdown links/fences。
- requirements/OpenAPI drift check。
- 前端 lint。
- 后端目标测试。

完整 Benchmark 和 build 仍由 CI 负责，避免提交钩子过慢。

## 提交拆分

建议保持可审阅的小提交：

1. `chore(deps): regenerate requirements from uv lock`
2. `chore(api): generate and verify FastAPI OpenAPI`
3. `security(config): separate secrets and local admin config`
4. `chore(mcp): split example and local MCP config`
5. `fix(front): resolve hook correctness lint errors`
6. `chore(front): restore lint gate and route override`
7. `chore(python): normalize uv indexes and pydantic settings`
8. `ci: add tests, generated artifact and docs checks`

每个提交都应保持现有测试和 smoke benchmark 通过。不要把 requirements、OpenAPI、安全迁移和 40 个 lint 修复压成一个不可审阅提交。

## 验收矩阵

| 范围 | 命令/检查 | 目标 |
|------|-----------|------|
| Backend lock | `uv lock --check` | pass |
| Backend requirements | regenerate + diff | no diff |
| Backend tests | `uv run pytest -p no:cacheprovider` | all pass, no target warning |
| Backend lint | `uv run ruff check app tests` | pass |
| OpenAPI | static vs `app.openapi()` | exact match |
| Django lock | `uv lock --check` | pass |
| Django requirements | regenerate + diff | no diff |
| Django check | `uv run python manage.py check` | no issues |
| Front lint | `npm run lint` | 0 errors, 0 warnings |
| Front tests | `npm run test` | all pass |
| Front build | `npm run build` | pass in clean output |
| Benchmark | smoke offline | 4/4 or updated reviewed baseline |
| Docs | links, anchors, fences | pass |
| Git | generated/local config | no unexpected diff |

## 回滚策略

- requirements：回滚生成提交并恢复对应 lock，不单独回滚其中一个文件。
- OpenAPI：导出脚本和静态文件作为同一提交回滚。
- encryption key：保留旧 key 和数据库备份，确认全部密文重加密后才能销毁旧 key。
- security/MCP local config：迁移前保存本机副本，失败时恢复配置路径，不提交副本。
- lint：每批按页面回滚，不能用全局规则关闭掩盖失败。
- CI：先作为非阻断检查观察一次，再转为 required check；安全和生成物检查可直接阻断。

## 结束条件

所有验收矩阵通过，CI 被设为合并必需检查，且连续两次依赖或路由变更没有再次产生 requirements/OpenAPI/文档漂移后，本计划可标记完成并移入 `project_changes/` 归档。
