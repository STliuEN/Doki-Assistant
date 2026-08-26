# 2026-08-26 Baseline File Inventory

This inventory is the auditable scope for the 826 cross-review execution batch.
It was captured against `HEAD=22a009f8b9ab16da786be6e63781775c8124ab84` with
parent `cc9be2f3ebfffa97781f11f17a28972d7b9fe3f1`. Hashes are SHA-256 of the
current file bytes. The tracked diff and status counts are authoritative in
`baseline.json`.

The old review number of 123 business files is not reused. Every current
tracked modification and untracked file is listed below. The inventory file's
own hash is intentionally excluded to avoid a self-referential digest; its
path and ownership remain in scope.

| Path | Status | Batch ownership | SHA-256 | Bytes |
|---|---|---|---|---:|
| `README.md` | modified | P0-4 R7 baseline wording | `d7950a44264c0e170ea0fdce65d0fa3fa3b6334beba57fc82906dbd2c516ca6b` | 15941 |
| `backend/app/agent/mcp/config.py` | modified | P0-3 MCP authority boundary | `484045859885fc16a6d7dedfab0efc21a9bfca5f88adade006e5a11840144005` | 13318 |
| `backend/app/agent/mcp/provider.py` | modified | P0-3 MCP discovery/call fail-closed | `856122c8443ff37f69038cf269898f0bb0f799934577e4e18dd37d4bc5ad7203` | 13062 |
| `backend/app/agent/mcp/registry.py` | modified | P0-3 MCP cache boundary | `6210ae3933f7737426570d41baee5322d41e474ae2a52bafe53bc542e45fb180` | 3802 |
| `backend/app/agent/tool_guard.py` | modified | P0-3/P1 tool digest and confirmation boundary | `3437e5e9b6ca7c626e2fdc3d915c29675393ed22d67b7b2a061890c92a1e1a77` | 12875 |
| `backend/app/core/background_init.py` | modified | P0-1 Chroma background isolation | `ee827d23f3c2683e91c1ae5bad8167c12771654c5ca6ed1f69ac6da489be619b` | 4963 |
| `backend/app/rag/vector_store.py` | modified | P0-1 Chroma preservation/readiness/rebuild | `944cc770eaf8b39e69e37940f9faef64cc2f7d84d6e61e4a68df2756aee0962c` | 31146 |
| `backend/app/router/health.py` | modified | P0-1 layered readiness response | `f76ba03e0e493d24caa9e417f0831d0549d198f7d111bbd8aba3d9e894310f74` | 2042 |
| `backend/app/router/mcp_router.py` | modified | P0-3 MCP management fail-closed | `d2f627c015bc55f4f69c7266988b3f7c19e54b7ead94161eedf44c12d16a14bb` | 8905 |
| `backend/app/router/note_router.py` | modified | P0-1 NoteService readiness/failure contract | `fe1bab81da93eaaf906e73f08b3c9721070a70f75812a4ee71fc2d2b8a491e0a` | 14301 |
| `backend/app/router/skill_router.py` | modified | P0-2 Skill mutation/error contracts | `53cda56fec8ba21d5e294e4b7a0ec54624ef485397922c5a2cf6dca58ae4b79e` | 14391 |
| `backend/app/services/confirmation_service.py` | modified | P0-3/P1 confirmation digest boundary | `d030a69dad26c4901d5560ef021381124db1cbb96bd52d8a9a65c5b7e105c6af` | 5976 |
| `backend/app/services/note_service.py` | modified | P0-1 shared Chroma owner | `8cdcdb4cca188d05f566ec901f032955fb46262d1ac38c2d2e98f31206ae6f58` | 25338 |
| `backend/app/skills/registry.py` | modified | P0-2 healthy/degraded snapshot isolation | `f3359d2ffd05685ce1d104e357a6e4cc1035d4a2c0366e36cbb800823f71faad` | 7430 |
| `backend/app/skills/schema.py` | modified | P0-2 installed-disabled response state | `4d80819502b4c8d3d0f36bfc1eebcd87233f97c9cdc7574505dc3c6a20627852` | 12159 |
| `backend/app/skills/service.py` | modified | P0-2 digest preflight/import containment/Registry fail-closed | `80f79be28f97145c0faf660f16556fddacf658d968a5282e70e4b22a0961c119` | 68584 |
| `backend/main.py` | modified | P0-2 CORS and lifecycle wiring | `867ece170d1a5d8d4f2c299d7b8d089fb6f72172b4ad355683dec27218905763` | 7827 |
| `backend/openapi.json` | modified | P0-2 generated error/media contracts | `f2113ed3f7740cb3b5ecd1625195bc85c43da9d4e769a8132348ced4f9061b03` | 243087 |
| `backend/scripts/backup_restore.py` | untracked | P0-5 offline backup/restore and projection rebuild | `0314a567a4a2fe624a18a3f1f53b0dbbc21d17f2f8ce4bdf1a6783524f94e83d` | 18183 |
| `backend/tests/test_api_contracts.py` | modified | P0-2 API error/CORS regression coverage | `acb80b06a14d0ea26d2e481a782d093351387b2dda44cb1c7c150958c18b35a2` | 5090 |
| `backend/tests/test_backup_restore.py` | untracked | P0-5 manifest/round-trip/tamper coverage | `00cafb5e23ead23e8a0a5ce6b5daa38adcdf9e1e1446de565a190a2dc346bb2b` | 11231 |
| `backend/tests/test_chroma_containment.py` | untracked | P0-1 failure isolation/restart/rebuild coverage | `aef893ab9cc418491d5f0caa5c4d4eca1b5f13a20d8b1e944e6debe9ffa5f437` | 8820 |
| `backend/tests/test_skill_router_containment.py` | untracked | P0-2 endpoint 415/413/409 containment coverage | `5f9e7d919882a4a946b1d32361b4823a26122622a8a21cc0f1e3c479dad8f16d` | 3197 |
| `backend/tests/test_config_boundaries.py` | modified | P0-3 YAML authority boundary coverage | `fa93e55817772e9c909e5ddb71aa92d1b9109bdb2cf1bbbd4c4b076f40fd517f` | 7511 |
| `backend/tests/test_skill_registry_errors.py` | modified | P0-2 degraded registry/503/OpenAPI coverage | `109d0969dd6cdebc6708a23479aa1bfe4ed1da08272db54891902499f0adb76e` | 3133 |
| `backend/tests/test_skill_service_transactions.py` | modified | P0-2 import/publish digest and transaction coverage | `460401599ee9a6c0528cee58b60b3878e44cad6df3b4e30102cfb5eda742672d` | 28312 |
| `backend/tests/test_standard_skill_registry.py` | modified | P0-2 snapshot containment coverage | `9059d05506dd4ed816a554d4226c3ea2fd876708afc35316e303f058be679c4e` | 5521 |
| `docs/architecture_rewrite_plan.md` | modified | AR/SK sole status source and P0 gate updates | `9b86a4836c4c0911cb9b63c63c12490dc631ef7720c7ccceb016e0de1eeb5e36` | 17977 |
| `docs/backup-restore-runbook.md` | untracked | P0-5 isolated runbook | `21cd31124cdbf22b4711b0c724afc6b22939b20dd49c296a85e08e6b9c1df0aa` | 4264 |
| `docs/change-route-execution-plan-2026-08-26.md` | untracked | temporary P0/P1 execution plan | `cf764bb4b4edfa8a957e305aa636cb2430dfa9d4f59a67e91d327dee91e36c9d` | 5644 |
| `docs/change-route-review-2026-08-26.md` | untracked | review input; not implementation ownership | `348aea94696278643ada96e6157663fc9363a1fef94459b93a65fc1d1d640bb1` | 16568 |
| `docs/development_setup.md` | modified | P0-3/P0-4 environment and authority notes | `cebb2d65d38420b7d9e4ac07fc3b27a1170cb5163788d6ceb8457739862422ad` | 14311 |
| `docs/legacy-skill-inventory-2026-08-26.md` | untracked | P1 Legacy read-only inventory | `421decc0773d26bdaccf1e7bc40afd1a827af5ccbba6ed624d721473f660c6fc` | 6991 |
| `docs/p0-completion-report-2026-08-26.md` | untracked | P0 completion report | `7c354ac7456563818f0ef55d15f2d0055cbcedcb1c460bbdb007847e5d6c7246` | 4325 |
| `docs/roadmap_next.md` | modified | R7 current evidence status | `b23a238978f4504c8ae34cfa6be304664be297075e9613889e03a8fd71a05853` | 5094 |
| `docs/mcp_integration_plan.md` | modified | P0-3 YAML adapter/cache contract | `b460c69a422a63993736a467b02c84cea251353e015d1c8ab7a3d87a1196a144` | 13050 |
| `docs/project_develop.md` | modified | P0/P1 current-state and freeze notes | `a53407eb48c16e0c0029086f78bdce9fec012e7567161dcb5df467dfeae46b85` | 19427 |
| `docs/security_hardening_plan.md` | modified | gate and residual-risk corrections | `f5c2403ede4699c6c33c8af39a1a98dd6fed79dc4a0cd26cc722d17ae3cb70d8` | 13406 |
| `docs/skill-precutover-rework-matrix-2026-08-26.md` | untracked | P1 parser/domain/outbox return-work matrix | `1a889be2264d3338006f618682ec82787661116a61cfd72cab38274e787ca0bc` | 5079 |
| `docs/standard_skill_integration_requirements.md` | modified | SKILL-GATE and authorization contract | `30c0cc1d4f986bb8118120db32077bc242899b863a4457e539874888b909601a` | 44240 |
| `docs/troubleshooting.md` | modified | P0-3 authority/readiness diagnostics | `fe69ed30fa5e943d8cf21ba152801cb8a431350cdddf33e501e9180ad63fb5a0` | 16297 |
| `project_changes/2026-08-24-standard-skill-core-rewrite/test-record.md` | modified | prior-batch OpenAPI wording correction | `30ddcc459a22888716e8e0e5d327c9491ee1e6d7ca5e87c8e86b4e12c354b382` | 4211 |
| `project_changes/2026-08-25-plan-reality-alignment/change-log.md` | modified | prior-batch final change evidence | `d9f2b44546b7fa583a2393627a063eda34060ab977422b474917642cc479fc61` | 1948 |
| `project_changes/2026-08-25-plan-reality-alignment/test-record.md` | modified | prior-batch final command evidence | `dbcbbf48e9dff720acea5ba08ac17dfb7db68df8e28a32d63659664f440faf91` | 1859 |
| `project_changes/2026-08-26-change-route-execution/baseline.json` | untracked | P0-0 fixed baseline | `109f479341126a07a4b5b00d6c25441ea3578597e5d6f19d9e7ae4be002545db` | 7018 |
| `project_changes/2026-08-26-change-route-execution/change-log.md` | untracked | this batch implementation log | `dd14b76528877cf39a493a6376809705c7691e40bfa8afad702ade7e6dcf141b` | 4258 |
| `project_changes/2026-08-26-change-route-execution/file-inventory.md` | untracked | this inventory; self-hash excluded | `self-hash-excluded` | n/a |
| `project_changes/2026-08-26-change-route-execution/plan.md` | untracked | this batch ordered task ledger | `d6e420896b69d731ffd4780f3c9849124e24e2d06a76cbc22cb01e6b4f65248b` | 1419 |
| `project_changes/2026-08-26-change-route-execution/test-record.md` | untracked | this batch test evidence | `ba02da1e4a9b4fbb6c825d6873c728ac8611085c0fe26965118f1d9816c19ce0` | 9506 |

## Exclusions and reconciliation

- The historical 123-file claim is an input finding, not a current file set.
- Gitignored virtual environments, caches, generated local data, and secrets are excluded because they do not appear in `git status --porcelain=v1`.
- No current business path is left unassigned. The review report is explicitly classified as input-only; all code/test changes are assigned to P0/P1 work above.
- Any later change outside this 49-file scope requires a new batch or a P0-6 stop and C3 escalation.
