# 修改记录

## 新增脚本

- 新增 `scripts/start-all.ps1`
  - 检查项目目录。
  - 检查 MySQL、Redis、Ollama、Django、FastAPI、Frontend 端口。
  - 自动启动 Redis、Ollama、Django、FastAPI、Frontend。
  - 每个服务在独立 PowerShell 窗口运行。
  - 支持参数：
    - `-SkipRedis`
    - `-SkipOllama`
    - `-SkipFrontend`
    - `-SkipBackend`
    - `-SkipUserService`
    - `-NoReload`
    - `-FrontendPort`
    - `-BackendPort`
    - `-UserPort`

- 新增 `start-all.bat`
  - 作为根目录快捷入口。
  - 可双击运行，也可以命令行传参。

## 使用方式

```powershell
.\scripts\start-all.ps1
```

或：

```powershell
.\start-all.bat
```

跳过 Ollama 示例：

```powershell
.\scripts\start-all.ps1 -SkipOllama
```
