# 工作包 1 测试记录

日期：2026-08-17
状态：完成

## 专项验证

```text
python -m pytest backend/tests/test_knowledge_image_paths.py -q
17 passed
```

专项测试覆盖合法 MD5、非法 MD5、`..`、反斜杠、编码后路径、绝对路径、盘符路径、非图片扩展名、根/用户/MD5/文件级符号链接、读取不创建目录，以及批量文件数和总大小预算。路径相关 Ruff 检查通过。

## 最终发布门禁

| 检查 | 结果 |
|------|------|
| Backend pytest | `118 passed` |
| Backend Ruff | 通过 |
| Django | SQLite + `LocMemCache` 下 system check、migration drift 和 `19 passed` |
| Frontend | `20 passed`，lint 与 `dist-build-check` 构建通过 |
| FastAPI OpenAPI | 生成物与当前应用一致 |
| Alembic | `20260817_0001 (head)`，offline SQL 生成通过 |
| Offline Benchmark | smoke `4/4`；regression `117/117`，hard veto `0` |

## 结论

合法图片仍沿用原目录结构；目录穿越、跨根路径、目录链接/junction、文件链接和资源预算越界均被拒绝。全量回归通过，验证过程未连接或修改现有 MySQL。
