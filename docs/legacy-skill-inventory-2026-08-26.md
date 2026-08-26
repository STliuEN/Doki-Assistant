# Legacy Skill 只读 Inventory（2026-08-26）

状态：已从 Git 历史导出；仅证明历史输入可复核，不证明迁移完成。

## 来源与边界

- 分支：`ai_document_assistant`。
- 删除提交：`cc9be2f3ebfffa97781f11f17a28972d7b9fe3f1`（`backend/app/agent/skills` 删除）。
- 最后包含旧目录的提交：`1fa19f9acd8fcaa2c75e5de9ac2fe077bab9e6c9`（删除提交的父提交）。
- 导出范围：该提交树中的 `backend/app/agent/skills/**`，共 20 个文件、9,271 字节。
- 组合摘要：对按路径排序的 `path<TAB>bytes<TAB>sha256` UTF-8 清单逐行拼接后计算 SHA-256：`ba8faf6da1223fb5c412dc9363ee24f57bde0400dd70dc4f3a58e1e5bbb22241`。

复核命令（只读，不恢复旧运行目录）：

```powershell
$source = '1fa19f9acd8fcaa2c75e5de9ac2fe077bab9e6c9'
git ls-tree -r $source -- backend/app/agent/skills
git show "$source`:backend/app/agent/skills/memory_read/skill.yaml"
git diff --name-status "$source^" $source -- backend/app/agent/skills
```

下表的 Git blob OID 来自 `git rev-parse <commit>:<path>`；`sha256` 是导出文件的内容摘要。两种摘要均用于发现输入变化，不是迁移成功证明。

## 文件清单

| 路径 | 字节 | SHA-256 | Git blob |
|---|---:|---|---|
| `backend/app/agent/skills/knowledge_research/SKILL.md` | 318 | `bf80e50f4465793d5270dd1ce93d5c8e83aa929fe76f785b3ef2db176ef39b2e` | `e88b425335f48d96c39b440f06dc9050e625f42d` |
| `backend/app/agent/skills/knowledge_research/skill.yaml` | 334 | `40a08e6cb03de6cade529fed35c590b72c3a2cf626f959930d0be82de3f459f3` | `f8b170b05bbe1b364b7222b5c1bb57bc72b18271` |
| `backend/app/agent/skills/mcp_smoke_test/SKILL.md` | 722 | `1200c98209a8f5b7772827867bce2aa3b8df2fc9dbb93b04a52170d1ae55a5e5` | `ebcc73333439f6247f9d51f4291658b753a2bf19` |
| `backend/app/agent/skills/mcp_smoke_test/skill.yaml` | 382 | `02bbc4e19d3d2b23c90d8d1d94d42040a2e10582bf3b836a6ddf1580fcfe6a89` | `2a2e8b692352a725506cc79f1b112324776cc1b8` |
| `backend/app/agent/skills/memory_cleanup/SKILL.md` | 448 | `6ab545c1d272dae30e5d32de9c466ed401107a1eded41cb8df3086dcd2897b0f` | `394e2991f2fd7ef325044c17113413de64b1b685` |
| `backend/app/agent/skills/memory_cleanup/skill.yaml` | 460 | `0106602e1468eac7ba619f871a0dd605f2e195a13d0c805aec1f90d55d7f02df` | `e856bbacd907e371b7723fb61b8e85d14c151284` |
| `backend/app/agent/skills/memory_read/SKILL.md` | 420 | `b2eac5917ac3466aed81c9cde4b41feff274b7cae761d7e55e616bd8546306a9` | `cc46d3700cc4952330ac97fe3c055b3301e8ce85` |
| `backend/app/agent/skills/memory_read/skill.yaml` | 389 | `d2ca34eac35260305d8285a135d2f843f48cd495e3474cb809cd0e8720862f09` | `1ff143e4ed5407a382ba2f60c54e1828c6f96fb9` |
| `backend/app/agent/skills/memory_write/SKILL.md` | 678 | `9018996b734afd4f0597be363fa56cc804207b0faecec4f956b3fd2acf6ef3be` | `7b54fbaf138cc89cbfd43ee98fe3c1eef4bebab5` |
| `backend/app/agent/skills/memory_write/skill.yaml` | 518 | `943b283b67f47306487fb5af0a341bf2613d40de03ff3158c8d8326f9a690595` | `661a3e1e35540cdbe3025f44ecec1b1357500025` |
| `backend/app/agent/skills/note_research/SKILL.md` | 396 | `cacc25a322c54ebd8258270b3b61fe221e9ba165f34fe21484166260ce978d9c` | `4911cf36cb2059ddf9596ac09f09f8faa1f8009c` |
| `backend/app/agent/skills/note_research/skill.yaml` | 341 | `8023695abec911025be0165307f4df5d5e04747a3ff1ecc5262a9f6ce8ea83a6` | `c75d232c4fc61cb7bc7a4f82e089a47d7320f6d1` |
| `backend/app/agent/skills/note_writer/SKILL.md` | 294 | `27c0b206e585f1605656edca8a098406b88044e7808bd1e399cf24c0526d89a0` | `cb4c3258feed9b7c65ee4249f6c5e6205aace1b4` |
| `backend/app/agent/skills/note_writer/skill.yaml` | 315 | `c1dbdd408e921d5fba362b944955e5fdc3d239409685d00644cf9064561f1a94` | `dfffe30d5bd0dc5f2fe7d6b11f281c9ec2263510` |
| `backend/app/agent/skills/public_info_lookup/SKILL.md` | 987 | `798923ac538fc5723bb1e74f98b9204fca024a38ce9e0ce1af93958f272a9eb6` | `a902e3f58e25ea84dc4734d7af135efc788f669a` |
| `backend/app/agent/skills/public_info_lookup/skill.yaml` | 436 | `5f09c6881b9cd70e083fa0919939695579a8552a91cb28891637cc178bb76595` | `11ae6ec46b3c8f971239a75d915d7808acd95388` |
| `backend/app/agent/skills/review_planner/SKILL.md` | 631 | `6b0b33d60d958cfeea3b4ee6319b1826600260069845ae65c00e15f36418e18a` | `158fb1340f2131223aa11c73785118d4af1583aa` |
| `backend/app/agent/skills/review_planner/skill.yaml` | 474 | `c64e7a93ffb6f48bee0b91f8b7eb133712743ccbc9d18fbaaa2b6054baf9e788` | `e10e1a78dddaa3e0fb4cae82e2222e531b1bd4c6` |
| `backend/app/agent/skills/system_context/SKILL.md` | 422 | `979700f398321d98c550c79e32ec09e8cce334d8d32205a2c3d867cac7aa7950` | `73593f93d9b5c2e6121bc83a8f5806db08c4ece5` |
| `backend/app/agent/skills/system_context/skill.yaml` | 306 | `8874edfa19414e06c6ede810302282465ff717fac560bd31e7188cbcffaf1bff` | `a624ee7605623282331f517c20521469bb6a70f5` |

## 内容级摘要

旧目录包含 10 个 Skill，每个通常由 `SKILL.md` 和 `skill.yaml` 配对组成。YAML 提供旧 `id`/alias、label、description、Tool 列表、default、visibility、order、`always_on`（仅 `system_context`）和 routing examples。Tool 绑定包含记忆、笔记、RAG、MCP 和公开信息查询能力。

| Legacy alias | Tools | default | order | 特殊字段 |
|---|---|:---:|---:|---|
| `system_context` | `current_time`, `user_info` | true | 10 | `always_on: true` |
| `knowledge_research` | `rag_summary` | true | 20 | - |
| `note_research` | `search_notes`, `note_stats`, `related_notes` | true | 30 | - |
| `note_writer` | `create_note`, `search_notes` | true | 40 | - |
| `memory_write` | `current_time`, `create_memory`, `list_memories`, `get_memory`, `update_memory`, `complete_memory`, `postpone_memory` | true | 50 | - |
| `memory_read` | `current_time`, `list_memories`, `get_memory` | true | 51 | - |
| `memory_cleanup` | `current_time`, `list_memories`, `get_memory`, `archive_memory`, `delete_memory` | false | 52 | - |
| `review_planner` | `current_time`, `today_reviews`, `list_memories`, `get_memory`, `mark_memory_reviewed`, `postpone_memory`, `generate_review_question` | true | 60 | - |
| `mcp_smoke_test` | `mcp_powershell_ls_test_list_project_files` | true | 90 | MCP provider binding |
| `public_info_lookup` | `mcp_public_info_lookup_query_university_info`, `mcp_public_info_lookup_ping_check` | false | 95 | MCP provider binding |

这 10 个 YAML 均为 `visibility: public`，且都有 positive routing examples。与当前 `seed_manifest.py` 的表面字段对照显示 alias、Tool、default、visibility、order、always_on 和 positive routing examples 相同；这只是仓库内置 seed 的静态对照，不覆盖用户修改、安装设置、数据库 scope/owner、历史 policy/grant 或 MCP endpoint/config revision。

该清单不包含用户自定义 Skill、运行时安装设置、数据库记录、外部 Storage 对象、历史 Tool/MCP policy 或旧 Registry 快照；这些输入仍须从只读备份/发布归档/数据库盘点中另行确认。不得用当前 seed package 或本清单静默填补缺失字段。
