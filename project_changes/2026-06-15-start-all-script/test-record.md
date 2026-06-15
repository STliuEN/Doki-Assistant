# 测试记录

## 静态检查

已检查脚本路径和项目目录结构：

- `backend`
- `DjangoUserService`
- `front`

## 未直接启动服务

本次没有直接运行全套服务启动脚本，避免在当前会话中打开多个长期运行的 PowerShell 窗口。

## 建议用户验证

在项目根目录运行：

```powershell
.\scripts\start-all.ps1
```

然后访问：

```text
http://127.0.0.1:3000
http://127.0.0.1:8000/docs
http://127.0.0.1:8001/docs/
```
