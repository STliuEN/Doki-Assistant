# 全套服务启动脚本计划

## 目标

为当前项目增加一个 Windows 可用的全套服务启动脚本，用于日常真实使用。

## 范围

脚本需要启动或检查：

- MySQL：只检查端口并提示，不强行启动系统服务。
- Redis：如果 `redis-server` 可用且端口未运行，则新窗口启动。
- Ollama：如果 `ollama` 可用且端口未运行，则新窗口启动。
- Django 用户服务：`127.0.0.1:8001`。
- FastAPI 后端：`127.0.0.1:8000`。
- React/Vite 前端：`127.0.0.1:3000`。

## 文件

- `scripts/start-all.ps1`
- `start-all.bat`

## 设计

- 每个长期服务使用独立 PowerShell 窗口运行。
- 已运行的端口不重复启动。
- 支持跳过部分服务。
- 输出前端、FastAPI docs、Django docs 地址。
