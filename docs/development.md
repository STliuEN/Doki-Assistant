# 本地开发指南

本指南说明当前 Windows 工作区的依赖安装和启动方式。应用入口是 React 前端和 FastAPI 后端，数据由 MySQL 持久化。

## 环境准备

| 依赖 | 当前要求 |
| --- | --- |
| 系统 | Windows；后端 uv 配置限定 Windows 平台 |
| Python | 3.12，使用 uv 管理依赖 |
| Node.js | 建议 22.12+；当前启动器使用 `C:/nvm4w/nodejs/node.exe` |
| MySQL | 当前工作区使用 Docker 中的专用实例 |
| Redis | 开启限流时需要；当前启动器使用 `127.0.0.1:18020/3` |
| 模型 | 当前启动器使用 Ollama `qwen3:0.6b`；检索另需 Embedding 模型及对应重排模型缓存 |

从仓库根目录执行：

```powershell
uv sync --project backend --extra dev
npm --prefix front ci
```

环境变量模板在 [`backend/.env.example`](../backend/.env.example)。根据所需模型填写本机配置，已有 `backend/.env` 时保留其中的配置和密钥。数据库凭据、认证密钥和模型密钥不写入文档或 Git。

## 启动现有工作区

当前启动器 [`start_development.py`](../backend/ops/e6_e7/start_development.py) 依赖本机已经完成迁移的 MySQL、`.runtime/e4/` 中的私有凭据和认证密钥，以及已安装的 Node 路径。它会校验目标身份并生成新的 preflight；这是现有工作区的启动入口，不是全新机器的一键安装器。

确认 MySQL、Redis 和所用模型服务已运行后，从仓库根目录执行：

```powershell
$dokiRun = '.runtime/dev-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/start_development.py --directory $dokiRun --enable-runner
```

`--enable-runner` 启动后台 SQL 任务消费者，用于文档索引和其他排队任务。启动器创建 FastAPI 与 Vite 进程，日志和进程信息保存在 `$dokiRun`。若端口已被占用，启动器会拒绝替换现有进程。

| 入口 | 地址 |
| --- | --- |
| 工作台 | <http://127.0.0.1:18080> |
| API 文档 | <http://127.0.0.1:18000/docs> |
| 就绪检查 | <http://127.0.0.1:18000/health/ready> |

查看启动结果：

```powershell
Get-Content -Encoding utf8 (Join-Path $dokiRun 'backend.err.log') -Tail 40
Invoke-RestMethod http://127.0.0.1:18000/health/ready
```

停止这一轮启动的服务：

```powershell
& backend/.venv/Scripts/python.exe -X utf8 backend/ops/e6_e7/stop_development.py $dokiRun
```

停止脚本使用该目录中的进程记录。不要用旧运行目录停止新服务。

## 新环境与历史入口

新机器需要准备专用 MySQL、迁移 schema、配置密钥并建立与目标匹配的运行配置。当前启动器绑定既有本机资源，不能仅复制 `.env` 就在新机器复现。数据库与恢复流程见 [运行手册](../project_changes/2026-09-15-e8-ar6-preparation/e8-runbook.md)。

根目录 `start-all.bat` 和 `scripts/start-all.ps1` 仍属于历史多服务启动流程，会启动 Django 并探测主机 3306；它们不作为当前单 FastAPI 工作区的推荐入口。普通 `uvicorn main:app` 命令也不会自动注入上述运行配置。

数据库操作仅针对已核对的 Doki 实例；不修改 MySQL 全局只读设置，不重启或修改本机 new-api 服务。

## 开发检查

在仓库根目录执行：

```powershell
uv run --project backend pytest backend/tests
uv run --project backend ruff check backend/app backend/ops backend/tests
npm --prefix front test
npm --prefix front run lint -- --max-warnings 0
npm --prefix front run build
```

涉及真实数据库、投影或恢复的改动，还需要在隔离副本完成对应验收。脚本入口与证据见 [文档索引](README.md)。
