# 2026-06-24 Skill 预路由 4b 校准变更记录

## 后端

- 更新 `backend/app/agent/routing_calibration.py`：
  - 新增 `CALIBRATION_VERSION = 3`，旧版本校准 JSON 自动失效。
  - 新增持久化阈值读取/写入，文件位于 `backend/data/routing_calibration/*.json`。
  - 缓存签名纳入 embedding identity、vector_dim、Skill 描述与 `routing_examples`。
  - 新增噪声样本池和 `noise_ceiling`。
  - 新增 `NOISE_DOMINANCE = 0.50`，只锚定主导噪声吸引子，避免散射噪声误抬低量纲 Skill floor。
  - 新增 `MAX_PERSISTED_CALIBRATIONS = 12`，限制历史校准文件无界增长。
- 更新 `backend/app/agent/intent_router.py`：
  - 新增索引构建锁，避免并发重建 `_skill_vectors`。
  - 打分时使用索引快照，避免路由与并发重建互相影响。
  - DIRECT 判定改为相对原始 top2 gap，而不是 floor 过滤后的 top2。
  - 原始 top1 被噪声 floor 挡下后，不允许顺位候选直接变成 DIRECT。
  - 噪声抑制场景交给 LLM 判空，不传递顺位 hints，避免把闲聊偏向第二名。
  - 收紧 `memory_read` 的泛化关键词：`查一下武汉大学哪年建校` 不再强制命中记忆查询。
  - 新增 `warmup_routing()`，优先预热默认 routable 集合，再补算全量 routable 集合。
- 更新 `backend/app/core/background_init.py`：
  - `embed_model` 初始化完成后调用 `warmup_routing()`。
- 更新 `backend/tests/test_intent_router.py`：
  - 新增 4b 噪声吸引子回归测试。
  - 新增散射噪声不锚定回归测试。
  - 新增泛化 `查一下` 不强制落 `memory_read` 回归测试。
  - 测试校准目录改为 `tmp_path`，避免污染本地 `backend/data/routing_calibration`。

## 配置

当前本地 `.env` 使用：

```env
EMBED_MODEL_TYPE=OLLAMA
TEXT_EMBEDDING_MODEL_NAME=qwen3-embedding:4b
```

## 文档

- 更新 `docs/development_setup.md`：
  - 默认 embedding 示例改为 `qwen3-embedding:4b`。
- 更新 `docs/project_develop.md`：
  - 重写 Skill 预路由与校准说明。
  - 记录 v3 参数、缓存签名、4b 噪声锚定行为和本地预热结果。

## 4b 本地校准结果

2026-06-24 使用 `qwen3-embedding:4b` 预热后：

| 候选集合 | global floor | global gap | knowledge floor | knowledge noise ceiling | unstable |
| --- | ---: | ---: | ---: | ---: | --- |
| 默认 routable Skill | `0.393041` | `0.047971` | `0.645064` | `0.605064` | `memory_write`, `review_planner` |
| 全量 routable Skill | `0.333354` | `0.030000` | `0.645064` | `0.605064` | `memory_cleanup`, `memory_write`, `public_info_lookup`, `review_planner`, `system_context` |

## 注意事项

- `backend/app/utils/factory.py` 与 `backend/app/services/embedding_config_service.py` 中无环境变量时的代码默认值仍是 `qwen3-embedding:0.6b`；正常运行以 `.env` 为准。
- `backend/app/utils/file_handler.py` 当前也处于未提交改动状态，但属于 DOCX 读取链路，不属于本次预路由校准范围。
