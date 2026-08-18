# 工作包 2 测试记录

日期：2026-08-17
状态：完成

## 专项验证

前端安全测试覆盖正常标题、强调、代码和链接，以及原始 `script`、带事件属性的图片、`iframe`、`javascript:`、`data:`、`vbscript:` 和空流式消息占位。历史消息与流式消息都通过统一的 `ChatMarkdown` 渲染路径验证。

```text
front> npm test
20 passed

front> npm run lint -- --max-warnings 0
passed

front> npm run build -- --outDir dist-build-check
passed
```

此前由既有 `front/dist` 文件占用引起的构建阻塞已通过项目内隔离输出目录复核，不再是发布阻塞。

依赖树复核时发现本机旧 `node_modules` 中仍有已从清单移除的 `rehype-raw` extraneous 残留；执行干净 `npm ci` 后，`npm ls` 不再报告 extraneous，随后再次运行的 `20` 项测试、lint 和构建全部通过。该残留未进入 `package.json` 或 lockfile。

## 最终发布门禁

| 检查 | 结果 |
|------|------|
| Backend pytest / Ruff | `118 passed`；Ruff 通过 |
| Django | SQLite + `LocMemCache` 下 system check、migration drift 和 `19 passed` |
| Frontend | `20 passed`；lint、生产构建通过 |
| FastAPI OpenAPI | current |
| Alembic | `20260817_0001 (head)`；offline SQL 通过 |
| Offline Benchmark | smoke `4/4`；regression `117/117`，hard veto `0` |

## 结论

危险 HTML 不会生成可执行 DOM，危险 URL 协议会被改写，标准 Markdown 与代码高亮保持可用。全量前后端与离线回归均通过。
