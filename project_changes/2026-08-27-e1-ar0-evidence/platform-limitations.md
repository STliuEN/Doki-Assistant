# E1 跨平台与运行环境限制

状态：待验证

## 已运行环境

| 维度 | 实际环境 | 结论 |
|---|---|---|
| 主机 | Windows 11 64-bit build 26100，PowerShell 5.1 | 已验证本机路径、ACL、进程和 Docker 编排行为 |
| Python/uv | Python 3.12.3、uv 0.8.17 | 符合 backend `>=3.12,<3.13` |
| Docker | Docker Desktop 4.77.0、Engine 29.5.3、Linux/amd64 | 已验证隔离 MySQL 8.4.11；不是原生 Linux 主机证据 |
| MySQL | `mysql:8.4`，解析版本 8.4.11 | `127.0.0.1:33307/33308` loopback 隔离恢复通过 |
| Node/frontend | Node 22.20.0、npm 10.9.3，来自 `C:\\nvm4w\\nodejs` 的显式 PATH | Vitest/lint/build 通过；默认 PowerShell PATH 不含 node |
| Browser | Playwright Firefox 1539 | login/register 与 mock Skill UI 表征完成；Chrome 不存在，不能宣称 Chromium 结果 |
| Chroma | 项目锁定 `chromadb 1.5.9`/`langchain-chroma 1.1.0` 依赖，E1 独立目录 | 真实写入、查询、重启、故障和恢复通过 |

## 未运行或不能外推

| 平台/能力 | 状态 | 原因与后续 |
|---|---|---|
| 原生 Linux | not-run | 只有 Docker Linux 内核；需独立 Linux 主机或 CI runner 复跑 ACL、路径、权限和 Chroma restart |
| 原生 macOS | not-run | 未提供 macOS 主机；需复跑 symlink、路径大小写、权限和 Docker Desktop 行为 |
| Chrome/Chromium 浏览器 | not-run | 本机 Chrome 不存在，改用 Firefox；需在目标浏览器复跑截图、console 和网络表征 |
| 真实 Django/FastAPI + 业务 MySQL UI E2E | blocked | 当前应用 lifespan 需要 schema revision `20260824_0002`；E1 禁止 migration 且不连接现有 `3306` 业务库 |
| 真实 LLM/Embedding/Reranker | not-run | E1 使用确定性向量，仅验证持久化/恢复合同；在线质量应另设门禁 |
| 高并发、HA、多实例和跨机时钟 | not-run | 目标是单机低并发；runner lease/fencing 属于 AR-1/E2 |
| RPO/RTO 数值 | not-run | 已完成 dump/restore/restore-forward，但未在批准的生产窗口测量时间目标 |

## Windows 特有观察

- Windows ACL deny-read 能稳定触发 Chroma quarantine；恢复 ACL 后显式重试可以 ready。
- E1 证据目录使用绝对路径约束；备份工具仍拒绝盘符、UNC、根路径、symlink 和已存在目标，路径规则同时由 fixture 覆盖。
- Node 通过显式任务 PATH 运行。默认 shell 找不到 `node`/`npm` 不代表前端失败，但复现命令必须注明 PATH 来源。
- Firefox 进程和 Vite 进程属于本次本地 characterization 资源；阶段收尾后停止测试服务，保留截图和日志。

## 复现要求

在其他平台复跑时必须保留相同 E1 证据 ID、隔离目录、合成数据、manifest digest 和命令输出；平台差异应新增记录，不得覆盖 Windows 结果，也不得把 fixture 路径测试当作原生平台证明。
