# 预路由自适应化改造计划

## 背景与目标

当前 `intent_router.py` 的规则表/白名单/权重全是硬编码，每加一个 skill 都要手改路由代码。
目标：**加新 skill 只写 `skill.yaml`，不碰路由代码**；同时修好现有"赢家通吃 / 兜底全集"导致的工具调用不顺。

## 真实嵌入校准结论（qwen3-embedding:0.6b，本地）

- 纯 description 语义路由：高区分度 skill（knowledge/note/public/mcp/review/system）干净命中 top-1。
- memory 三件套（read/write/cleanup）语义高度纠缠，gap 仅 0.02~0.07，**校准 description 也无法可靠区分** → 必须关键词兜底。
- 绝对分数基线差异大（public 真命中 0.40 vs 闲聊误命中 0.43）→ **禁用单一绝对 HI，改用 gap + 绝对下限**。
- 校准 description 对 public 提升显著（0.35→0.65），值得做，但要剔除"安排"等通用动词避免污染。

## 最终设计：语义为主 + 核心关键词保底 + 模糊带 LLM + 阶梯回退

### 1. 扩展 SkillDefinition / skill.yaml（可选字段，向后兼容）

`skill_registry.py` 的 `SkillDefinition` 加两个可选字段，`_load_skills` 解析：

| 字段 | 作用 | 缺省 |
|---|---|---|
| `always_on: bool` | 替代硬编码白名单，选中即常驻、不参与语义竞争 | `False` |
| `routable: bool` | 是否参与收窄路由（False=被选中就常驻不裁） | `True` |

- `system_context` 的 yaml 写 `always_on: true`，删掉 `intent_router` 里的 `ALWAYS_ON` 常量。
- 嵌入文本 = `label + "。" + description`（纯 description，不引入 examples 字段）。

### 2. 校准各 skill 的 description（纯文案，强化独有动作动词 + 边界）

重写以下 skill.yaml 的 description（强化区分度，剔除通用词）：
- `memory_write`：新建/创建/登记/记下提醒待办 + 完成/修改/更新/延期/推迟已有事项。
- `memory_read`：查看/浏览/列出已有事项清单与详情，只读不改。
- `memory_cleanup`：删除/移除/清除/归档/存档不再需要的事项。
- `review_planner`：去掉"安排"等通用词，强化"间隔复习/复习自测题/推进复习进度"。
- `public_info_lookup`：明确"中国大学公开资料 + 公网域名/IP 的 ping 端口检测"。
- 其余（knowledge/note_research/note_writer/mcp_smoke_test/system_context）微调即可。

### 3. 语义索引（放 intent_router，不污染 SkillRegistry）

- 模块级缓存 `{skill_id: vector}` + 内容签名（各 skill `id|label|description` 的 hash）。
- 懒构建：首次 route 且 `init_manager.embed_model` 就绪时，对未缓存 skill 批量 `embed_documents`；
  签名变化（加/改 skill）自动增量重建。照搬 `vector_store._LazyEmbedding` 的"延迟到就绪再算"。
- `embed_documents` 是同步调用，用 `asyncio.to_thread` 包装避免阻塞事件循环。

### 4. 核心关键词规则（精简，只守增删改查 + 复习推进）

保留一张**小而精**的关键词表（只覆盖语义证明纠缠的部分），命中给"强信号"：
- `memory_write`：记一下|记下|新建|创建|添加|加待办|提醒我|完成|做完|改成|修改|更新|延期|推迟|顺延
- `memory_read`：今天有什么|待办|清单|列一下|查一下|看看.*事项
- `memory_cleanup`：删除|删掉|删了|移除|清除|归档|存档
- `review_planner`：复习|背诵|自测|出题|考我|标记已复习
（knowledge/note/public/mcp 不写规则，纯靠语义——校准已证明够用。）

### 5. 路由流程（重写 route_skills）

```
candidates ≤ 1 或空 query → 原样返回
always_on 的 skill → 直接保留（不参与竞争）
对 routable 候选：
  ① 关键词命中 → 强信号集 strong
  ② embed 就绪 → query 嵌入，算余弦相似度
       sim 满足 (top1 ≥ FLOOR 且 gap ≥ GAP) → 语义直选集 semantic_hit
       FLOOR ≤ sim < 直选线 → 模糊带 ambiguous
  最终 = strong ∪ semantic_hit（并集，解决"赢家通吃"）
  若仅有 ambiguous（无强信号、无语义直选）→ 把 ambiguous 作先验交 LLM 仲裁
topN 截断 + 并入 always_on
```

阈值初值（按校准数据）：`FLOOR≈0.35`、`GAP≈0.10`、`TOPN=4`。模块常量集中，便于后续按日志调。

### 6. 阶梯回退（保住"绝不静默丢能力"）

```
embed 未就绪          → 仅用关键词 strong；strong 也空 → 全集
有 strong/semantic_hit → 用并集
仅 ambiguous          → LLM 仲裁（失败/无果 → 取相似度 topN）
全部低于 FLOOR 且无关键词 → 全集回退
未挂 skill 的游离 tool  → 常时露出（安全网，当前无此情况，防将来）
```

### 7. 测试（沿用 .venv + conftest.py）

mock `init_manager.embed_model` 返回确定向量，覆盖：
关键词强命中（记/删/查/复习）、语义直选、并集叠加、模糊带触发 LLM、
embed 未就绪退关键词/全集、always_on 常驻、topN 截断、绝不引入集合外能力、闲聊回退。

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `app/agent/skill_registry.py` | SkillDefinition 加 `always_on`/`routable` + yaml 解析（小改） |
| `app/agent/intent_router.py` | **重写**：语义索引缓存 + 关键词强信号 + gap/floor 判定 + 模糊带 LLM + 阶梯回退 |
| `app/agent/skills/*/skill.yaml` | 校准 description；`system_context` 加 `always_on: true` |
| `app/router/chat.py` | **不动**（route_skills 签名兼容） |
| `tests/test_intent_router.py` | 改写为语义+关键词混合路由测试 |

## 取舍与风险

- 阈值 FLOOR/GAP 是按本机校准数据给的初值，上线后拿真实 query 日志微调；但只调 2~3 个全局数，不随 skill 数变。
- 质量天花板仍是 description；本计划用"校准文案"把它拉到可用线，且 memory CRUD 由关键词兜底不依赖语义。
- 冷启动头几秒 embed 未就绪 → 关键词/全集回退，可接受。
- 关键词表是唯一保留的"半硬编码"，但只覆盖固定的增删改查核心，新业务 skill 不需要往里加（走语义）。
