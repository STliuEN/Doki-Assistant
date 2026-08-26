# 2026-08-26 Change Route Execution Log

Status: executed containment work; AR-0 + SK-0 remain open.

## Baseline

- Branch: `ai_document_assistant`.
- Fixed comparison: `HEAD=22a009f8b9ab16da786be6e63781775c8124ab84`, parent `cc9be2f3ebfffa97781f11f17a28972d7b9fe3f1`.
- Initial worktree had only the review report untracked. The final P0 execution scope contains 34 tracked modifications and 15 untracked files (49 files total), including this continuation's R7 wording updates and P0 report. The historical claim of 123 business files was not reused.
- Fixed `HEAD^..HEAD`: 22 files, `+585/-16643`; raw Git binary patch SHA-256 `3805c15008880bf152aee8fd812e844d7e9376dcfbe422fcf00e616d100b746d` (939240 bytes).
- Final tracked working-tree binary diff SHA-256 and byte count are regenerated after the final edits in `baseline.json`; this is an execution snapshot, not a clean-commit claim. Per-file ownership and hashes are in `file-inventory.md`.

## Implemented

- P0-1: Chroma initialization preserves projection bytes, records quarantine health, isolates background initialization, and exposes degraded readiness. NoteService uses the same VectorStoreService projection path and returns terminal `503` after failed initialization. Collection reset failures now stop rebuilds. Added an offline manifest-backed projection rebuild that stages and verifies a new generation, atomically swaps it, quarantines the prior generation, rolls back on swap failure, enforces the configured projection directory, and requires process restart rather than retargeting an active Chroma client.
- P0-2: import approval is always disabled through the existing `disabled` column plus `installation_state=installed_disabled`. Storage digest, manifest, metadata, and capabilities are revalidated before pointer changes and on idempotent published retries. Storage I/O failures are quarantined with a stable `503` route contract. Degraded Registry rebuilds preserve a healthy snapshot and do not acknowledge outbox events. ZIP media type, upload limit, idempotency conflict, lifecycle 400/404/409 responses, CORS, and OpenAPI contracts are declared and regression-tested, including isolated endpoint mappings for 415/413/409.
- P0-3: MCP YAML is runtime read-only adapter/cache. Without the future AR-3/AR-5 versioned authority, discovery, listing, calls, confirmation digests, refresh, and policy writes fail closed; server/tool responses expose `policy_authority` and `runtime_enabled` explicitly. Explicit local maintenance helpers do not authorize runtime execution.
- P0-5: added offline-only `backend/scripts/backup_restore.py`, manifest verification, cross-platform path traversal rejection, tests, and `docs/backup-restore-runbook.md` for MySQL dump fixtures, Storage trees, and Chroma projection trees.
- P1: updated R7 and gate boundaries, corrected 08-24 OpenAPI wording, and added Legacy inventory plus the precutover rework matrix.

## Follow-up containment audit

- P0-1: NoteService initialization now has an explicit terminal event. Model/Chroma failure wakes waiting Note routes, which return a stable 503 instead of waiting forever. User-index `reset_collection()` failures are logged and propagated; projection rebuilds reject targets outside the configured `persist_directory`.
- P0-2: Storage `OSError` during Skill import is quarantined as `storage_unavailable`; the route maps it to 503 without creating a Skill or Registry entry. Post-commit registry cancellation is characterized as a recoverable outbox-reconciliation state.
- P0-3: YAML-backed MCP server catalogs now expose `policy_authority=unavailable`, `status=policy_unavailable`, and `runtime_enabled=false` until the versioned authority exists; read-only adapter metadata is not presented as executable authorization.

## Deliberate non-completion

- No migration was added or executed. `SkillInstallationStatus` remains `enabled/disabled`.
- No AR-1 worker/UoW/lease/fencing/retry/DLQ, multi-instance, or public HA work was started.
- Frontend R7 is now verified with Node 22.20.0/npm 10.9.3 resolved from `C:\nvm4w\nodejs`; live MySQL/Redis/Storage/Chroma, online fault injection, and production recovery remain unverified.
- AR-0 exit is not declared; work packages 7-10 remain frozen.
