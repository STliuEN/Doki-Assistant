# E1 跨平台与运行环境限制

状态：已关闭

## 已运行环境

| 维度 | 实际环境 | 结论 |
|---|---|---|
| 主机 | Windows 11 64-bit build 26100，PowerShell 5.1 | 已验证本机路径、ACL、进程和 Docker 编排行为 |
| Python/uv | Python 3.12.3、uv 0.8.17 | 符合 backend `>=3.12,<3.13` |
| Docker | Docker Desktop 4.77.0、Engine 29.5.3、Linux/amd64 | 已验证隔离 MySQL 8.4.11；不是原生 Linux 主机证据 |
| MySQL | `mysql:8.4`，解析版本 8.4.11 | `127.0.0.1:33307/33308` loopback 隔离恢复通过 |
| Node/frontend | Node 22.20.0、npm 10.9.3，来自 `C:\\nvm4w\\nodejs` | 通过绝对 `node.exe` 路径运行 Vitest/lint/build；默认 PowerShell PATH 不含 node |
| Browser | Playwright Firefox 1539 | login/register 与 mock Skill UI 表征完成；Chrome 不存在，不能宣称 Chromium 结果 |
| Chroma | 项目锁定 `chromadb 1.5.9`/`langchain-chroma 1.1.0` 依赖，E1 独立目录 | 真实写入、查询、重启、故障和恢复通过 |

## 未运行或不能外推

| 平台/能力 | 状态 | 原因与后续 |
|---|---|---|
| 原生 Linux | out-of-scope/frozen | Windows 11 是唯一正式支持主机；Docker Linux 内核结果不外推，且不设原生 Linux 门禁 |
| 原生 macOS | out-of-scope/frozen | Windows 11 是唯一正式支持主机；未提供 macOS 主机，且不设原生 macOS 门禁 |
| Chrome/Chromium 浏览器 | not-run | 本机 Chrome 不存在，改用 Firefox；需在目标浏览器复跑截图、console 和网络表征 |
| 真实 Django/FastAPI + 业务 MySQL UI E2E | deferred-to-E3/E4/E5 | E1 不执行 migration；E2 只验证 schema/runner/恢复，认证、业务写入和 RAG 成功流分别在 E3、E4、E5 的批准环境验证，不阻塞 E1 |
| 真实 LLM/Embedding/Reranker | not-run | E1 使用确定性向量，仅验证持久化/恢复合同；在线质量应另设门禁 |
| 高并发、HA、多实例和跨机时钟 | not-run | 目标是单机低并发；runner lease/fencing 属于 AR-1/E2 |
| RPO/RTO 数值 | not-run | 已完成 dump/restore/restore-forward，但未在批准的生产窗口测量时间目标 |

## Windows 特有观察

- Windows ACL deny-read 能稳定触发 Chroma quarantine；恢复 ACL 后显式重试可以 ready。
- E1 证据目录使用绝对路径约束；备份工具仍拒绝盘符、UNC、根路径、symlink 和已存在目标，路径规则同时由 fixture 覆盖。
- Node 通过绝对 `C:\\nvm4w\\nodejs\\node.exe` 路径运行。默认 shell 找不到 `node`/`npm` 不代表前端失败，但复现命令必须使用该绝对路径或显式配置 PATH。
- Firefox 进程和 Vite 进程属于本次本地 characterization 资源；阶段收尾后停止测试服务，保留截图和日志。

## 复现要求

Windows 11 复跑必须保留相同 E1 证据 ID、隔离目录、合成数据、manifest digest 和命令输出。只有用户未来明确解冻 Linux/macOS 支持范围时才建立对应平台证据；新增结果不得覆盖 Windows 结论，也不得把 fixture 路径测试当作原生平台证明。
