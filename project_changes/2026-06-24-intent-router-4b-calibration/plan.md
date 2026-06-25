# 2026-06-24 Skill 预路由 4b 校准计划

## 背景

切换到 `qwen3-embedding:4b` 后，单个 Skill 的真实 query 与闲聊噪声整体仍可分；退化点集中在 `knowledge_research`：闲聊噪声会高分、稳定 top-1 落到该 Skill，并通过 gap 判定成为“自信直选”，绕过 LLM 仲裁。

原有 floor 主要锚定在正例分位数减余量，无法同时满足：

- `knowledge_research` 需要把闲聊噪声天花板挡住。
- `public_info_lookup` 等低量纲真实 query 需要保留召回。

因此需要在保留 per-skill 正例校准的基础上，引入噪声吸引子识别和模型/Skill 级阈值缓存。

## 目标

- 让 `qwen3-embedding:4b` 成为默认 embedding 配置。
- 对 `knowledge_research` 这类主导噪声吸引子抬高 floor，阻止闲聊 DIRECT。
- 避免 0.6b 式噪声散射误锚定 `public_info_lookup`，保护真实 query 召回。
- 切换 embedding 或修改 Skill 描述后自动使用对应阈值文件。
- 启动时预热默认 Skill 集合和全量 routable 集合，降低首轮请求抖动。
- 为 4b 黑洞、散射噪声、泛化查询关键词增加回归测试。
- 同步项目文档和改动记录。

## 非目标

- 不改变 Agent 工具调用执行链路。
- 不新增前端配置项。
- 不改 Skill/Tool registry 数据结构。
- 不处理 `backend/app/utils/file_handler.py` 中既有 DOCX 读取改动。
