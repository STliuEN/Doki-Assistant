# 2026-06-24 Skill 预路由 4b 校准测试记录

## 已执行

### intent router 单测

```powershell
cd backend
uv run pytest tests/test_intent_router.py
```

结果：

```text
15 passed
```

覆盖重点：

- `test_noise_attractor_does_not_direct_hit_or_promote_runner_up`
  - 模拟 4b 闲聊噪声稳定 raw top-1 落到 `knowledge_research`。
  - 验证噪声 floor 抑制后不会 DIRECT 到 `knowledge_research`，也不会顺位提升 `note_research`。
- `test_scattered_noise_does_not_anchor_floor`
  - 模拟 0.6b 式闲聊噪声散射。
  - 验证 `public_info_lookup` 低量纲真实 query 不会被偶发噪声 top-1 误杀。
- `test_generic_lookup_phrase_does_not_force_memory_read`
  - 验证 `查一下武汉大学哪年建校` 不会因泛化 `查一下` 关键词强制命中 `memory_read`。
- `test_dynamic_calibration_allows_model_specific_low_scores`
  - 验证动态 per-skill floor 能低于默认 `SIM_FLOOR`，保留低分真实 query 召回。

### 4b 校准预热

```powershell
cd backend
$env:TEXT_EMBEDDING_MODEL_NAME='qwen3-embedding:4b'
uv run python -c "import asyncio; from app.core.background_init import init_manager; from app.utils.factory import EmbedModelFactory; from app.agent.intent_router import warmup_routing; init_manager.embed_model = EmbedModelFactory().generator(); asyncio.run(warmup_routing())"
```

关键日志：

```text
EmbedModel 使用Ollama嵌入模型: qwen3-embedding:4b
【意图路由】噪声锚定抬高 floor: knowledge_research -> 0.645 (噪声 top-1 占比 100%)
【意图路由】阈值校准完成 floor=0.333 gap=0.030 unstable=['memory_cleanup', 'memory_write', 'public_info_lookup', 'review_planner', 'system_context']
【意图路由】噪声锚定抬高 floor: knowledge_research -> 0.645 (噪声 top-1 占比 100%)
【意图路由】阈值校准完成 floor=0.393 gap=0.048 unstable=['memory_write', 'review_planner']
意图路由预热完成（语义索引 + 阈值已就绪）
```

生成校准文件：

- `backend/data/routing_calibration/6f4b373a74cc841d76509aace31937a2972057c3231659eb7c33382572af6c69.json`
- `backend/data/routing_calibration/a87474022490187154172122f1b86088217fcc84585a0726ce424957c1c8f4fe.json`

## 未执行

- 未启动完整 FastAPI 服务做端到端聊天验证。
- 未用真实 DashScope LLM 检查 LLM 仲裁延迟和费用变化。
- 未做前端浏览器交互验证。

## 后续建议

- 启动后端后观察 `【意图路由】` 日志，确认普通闲聊不再携带 `knowledge_research`。
- 用真实聊天请求验证：
  - “你好 / 在吗 / 随便聊聊”只保留 `system_context` 或走普通对话。
  - “这份资料讲了啥”仍能命中 `knowledge_research`。
  - “查一下武汉大学哪年建校”在启用 `public_info_lookup` 时能命中外部信息查询。
