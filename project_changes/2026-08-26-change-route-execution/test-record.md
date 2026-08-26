# 2026-08-26 Change Route Execution Test Record

Status: P0-0 through P0-5 current-environment evidence complete; P0-6 gate review retains `AR-0 + SK-0`.

## Environment and limits

- Windows PowerShell; branch `ai_document_assistant`; fixed HEAD `22a009f8b9ab16da786be6e63781775c8124ab84`.
- Node `v22.20.0` and npm `10.9.3` are installed at `C:\nvm4w\nodejs` and were invoked with an explicit task-local PATH; frontend and browser evidence is verified below.
- No existing MySQL, Redis, Storage, or Chroma dependency was connected, mutated, migrated, or deleted. Live topology, fault injection, RPO/RTO, and restore-forward evidence remain blocked pending an approved isolated environment.

## Evidence metadata (machine-checkable)

Each row uses the same fields for executed and blocked checks. `owner` and
`approver` remain `pending` where the real environment has not been assigned;
that is an explicit gate blocker, not a completion claim.

| Evidence ID | Environment/version | Topology | Fixture/substitute | Command | Threshold | Actual/log reference | Owner | Approver | Status |
|---|---|---|---|---|---|---|---|---|---|
| `P0-0-baseline` | Windows PowerShell; Git worktree | HEAD plus parent; current worktree | porcelain status and SHA-256 inventory | `git status --porcelain=v1 -uall`; baseline JSON parse; inventory reconciliation | 34 tracked + 15 untracked = 49; every status path assigned | `baseline.json`, `file-inventory.md`; current status reconciliation | execution-batch | pending | verified-local |
| `R7-backend-regression` | Windows PowerShell; Python 3.12; uv lock | SQLite/mock/fixture only | pytest fixtures; no live services | `cd backend; uv run pytest -q` | exit 0; zero failures | `263 passed`; this record | execution-batch | pending | verified-local |
| `R7-static-contracts` | Windows PowerShell; Python 3.12; uv lock | source tree only | Ruff/OpenAPI/lock checks | `uv run ruff ...`; `uv run python scripts/export_openapi.py --check`; `uv lock --check` | exit 0; OpenAPI unchanged | passed; this record | execution-batch | pending | verified-local |
| `P0-1-chroma-fixtures` | Windows PowerShell; Python 3.12 | isolated temp directories; no live Chroma | corruption/permission/version/missing-collection/restart/readiness/reset/target fixtures | `uv run pytest -q tests/test_backup_restore.py tests/test_chroma_containment.py` | 30 passed; sentinel unchanged | `30 passed`; fixture tests | execution-batch | pending | verified-offline |
| `P0-2-skill-contracts` | Windows PowerShell; Python 3.12 | SQLite/mock/fixture only | tampered package, degraded registry, API route doubles, Storage I/O, cancellation | `uv run pytest -q tests/test_skill_registry_errors.py tests/test_api_contracts.py tests/test_skill_service_transactions.py tests/test_skill_router_containment.py` | 34 passed; fail-closed mappings | `34 passed`; fixture tests | execution-batch | pending | verified-offline |
| `P0-3-mcp-boundary` | Windows PowerShell; Python 3.12 | no versioned MySQL policy authority | YAML adapter/cache and provider doubles | `uv run pytest -q tests/test_config_boundaries.py` | authority absent => discovery/list/call/write denied | `13 passed`; no live authority | execution-batch | pending | verified-offline |
| `P0-5-backup-restore` | Windows PowerShell; Python 3.12 | isolated temp directories only | offline SQL dump, Storage tree, Chroma projection | `uv run pytest -q tests/test_backup_restore.py` | 18 passed; digest/round-trip/tamper checks | `18 passed`; fixture tests | execution-batch | pending | verified-offline |
| `P0-4-live-topology` | environment unavailable | MySQL/Redis/Storage/Chroma not connected | none approved | restore approved isolated topology first | real dependency baseline and fault injection | no log; blocked by environment | pending | pending | blocked |
| `P0-4-frontend-browser` | Windows PowerShell; Node `v22.20.0`/npm `10.9.3`; Playwright Chromium 152.0.7977.8 | local Vite server plus isolated Chromium session | `npm ci`; Vitest; ESLint; Vite build; login/register route smoke | explicit Node PATH; `npm ci`; `npm run test`; `npm run lint -- --max-warnings 0`; `npm run build`; Playwright CLI | clean install, 6 files/28 tests, zero lint errors, successful build, login and register pages with zero console errors | `output/playwright/p0-login.png`, `p0-register.png`; browser console had two React Router future warnings only | execution-batch | pending | verified-local |
| `P1-auth-audit` | contract frozen only | no unified role/grant/revoke authority | negative fixtures not yet approved | implement AR-2 and run API/worker/recovery reconciliation | complete audit fields and negative suite | no log; AR-2 prerequisite | pending | pending | blocked |

## Commands and results

| Command | Result | Evidence and limitation |
|---|---|---|
| `cd backend; uv run pytest -q` | `263 passed` | SQLite/mock/fixture coverage; no live dependency evidence. |
| `cd backend; uv run ruff check main.py app tests scripts` | passed | Static check only. |
| `cd backend; uv run python scripts/export_openapi.py --check` | passed | Current for declared routes, not full lifecycle proof. |
| `cd backend; uv lock --check` | passed | Current Windows resolution only. |
| `powershell -ExecutionPolicy Bypass -File scripts/check-docs.ps1` | `154 files, 125 local links` | Local Markdown/link check. |
| `git diff --check HEAD^ HEAD` | passed | Fixed commit scope; working tree is checked separately. |
| `uv run pytest -q tests/test_backup_restore.py` | `18 passed` | Offline fixture backup/restore/verify only. |
| `uv run pytest -q tests/test_backup_restore.py tests/test_chroma_containment.py` | `30 passed` | Offline manifest-backed projection rebuild, quarantine, rollback, restart fence, cross-platform path rejection, and Chroma failure isolation; no live Chroma or dependency evidence. |
| `uv run pytest -q tests/test_skill_registry_errors.py tests/test_api_contracts.py tests/test_skill_service_transactions.py` | `30 passed` | Lifecycle conflict/OpenAPI response contracts, Storage I/O quarantine, idempotent digest revalidation, and Skill containment transactions; no live API/browser evidence. |
| `uv run pytest -q tests/test_skill_router_containment.py` | `4 passed` | Isolated endpoint mapping for ZIP media type (415), upload limit (413), idempotency conflict (409), and Storage unavailable (503); no live API/browser evidence. |
| `uv run pytest -q tests/test_config_boundaries.py` | `13 passed` | YAML adapter/cache boundary, non-executable server metadata, and absent-authority discovery/call/write denial; no live authority. |
| `cd front; npm ci` | `545 packages added` | Node 22.20.0/npm 10.9.3 from `C:\nvm4w\nodejs`; lockfile install. |
| `cd front; npm run test` | `6 files, 28 tests passed` | Vitest current worktree regression. |
| `cd front; npm run lint -- --max-warnings 0` | passed | ESLint current worktree; no warnings/errors. |
| `cd front; npm run build` | passed | TypeScript build plus Vite production bundle. |
| `npx @playwright/cli open/snapshot/screenshot` | login and register smoke passed | Vite `127.0.0.1:18080`; Chromium 152.0.7977.8; zero console errors, two known React Router future warnings; screenshots under `output/playwright/`. |
| `uv run ruff check scripts/backup_restore.py tests/test_backup_restore.py` | passed | Backup tool static check. |
| `git diff --check HEAD` | passed | Final working-tree whitespace check; does not prove semantic correctness. |
| `uv run pytest -q tests/test_config_boundaries.py tests/test_skill_service_transactions.py tests/test_skill_router_containment.py` | `33 passed` | MCP YAML catalog boundary, Storage I/O quarantine, post-commit cancellation characterization, and stable 503 mapping; offline fixtures only. |

## Negative coverage

- Chroma: corruption, permission, incompatible version, missing collection, restart recovery, terminal note dependency failure, manifest-backed projection rebuild, configured-target enforcement, active-client retarget rejection, process restart fence, previous-generation quarantine, and tampered-bundle fail-closed; sentinel bytes remain unchanged.
- Skill: requested-enable containment, Storage tamper revalidation including idempotent published retries, Storage I/O quarantine, healthy and healthy-empty Registry preservation, degraded outbox non-ack, lifecycle 400/404/409 schemas, endpoint 415/413/409/503 mappings, ZIP media type, and CORS.
- MCP: absent versioned authority blocks discovery/list/call and confirmation authorization; adapter maintenance never grants runtime authority.
- MCP catalog: YAML server metadata is explicitly `policy_unavailable` and `runtime_enabled=false` when the versioned authority is absent; this is a visibility contract, not an authority migration.
- Backup/restore: three object fixture round trips plus repeat digest, tamper, POSIX/Windows path traversal, symlink, extra-entry, and target-conflict rejection.
- Skill failure isolation: Storage permission failure quarantines the import; cancellation after DB commit leaves the pointer durable and outbox reconciliation pending.

## Exit decision

P0-0 through P0-5 containment and current-environment regression evidence exists, including frontend/browser R7. Real dependency topology/recovery, cross-platform dependency evidence, the implemented unified authorization/audit flow, and remaining threat/characterization evidence are absent. P0-6 therefore retains `AR-0 + SK-0`; do not unlock AR-1 or work packages 7-10.
