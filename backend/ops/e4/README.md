# E4 isolated MySQL topology

## Current execution status: 2026-09-09

The local single-instance application cutover is executed, not merely configured.
Vite on loopback 18080 proxies to FastAPI 18000 (including `/jobs`); the running
application proves target database `doki_e4`, user `doki_e4_app@%`, and the exact
allowlisted target UUID. Django 18001 is a deployed retired/read-only boundary:
26 GET/POST probes return 410; ORM, migrations and a raw zero-row write are denied.
Source 3306 remains persistently read-only/super-read-only and its legacy account
is locked/revoked; its 21 table digests remain unchanged. An administrator can
explicitly remove these controls, so they are not an absolute administrator ban.

Three complete starts and two graceful stops prove runner lock and Redis-pool
release/reacquisition. Redis stop/recovery and Redis-down cold start are verified:
live/runner remain observable, readiness and rate-limited business requests fail
with 503, no business/job/audit mutations occur in the outage window, and restored
connections work without restarting the application. Auth alone is SQL-backed;
the final local profile explicitly enables rate limiting, unlike the first probe.

The final restore matches 39 tables and 2,539 rows. Backup SHA-256:
`bbcf14de7d4024aadc523d5e923fd73de917ad25c5396cf77c31b6c0d66a1b75`.
The original 312 business entities, 314 mappings and 48 FK constraints still pass.
Backend 502 tests, frontend 28 tests/build, Ruff and compileall pass.
See repository-relative
`project_changes/2026-09-02-e4-ar3-business-migration/artifacts/e4-full-lifecycle-cutover-20260908.json`.

Run the private local launcher from the repository root. It reads private secrets,
issues a fresh short-lived preflight and refuses an occupied port; E4 guard values
must be injected before dotenv. Merely editing `.env` or invoking the legacy
`scripts/start-all.ps1` does not grant E4 startup authority.

```powershell
backend/.venv/Scripts/python.exe .runtime/e4/app_runtime.py
backend/.venv/Scripts/python.exe .runtime/e4/app_runtime.py stop
```

Logs and PID/stop-marker references are in `.runtime/e4/active-app.json`. Wait for
shutdown before running target-to-restore rehearsal. Do not switch traffic back
to the old frozen source: new target auth/job/audit facts would be missing there.
No OS service manager or automatic reboot deployment is installed.

**Not certified:** production shared storage, DNS/load-balancer/TLS cutover,
or the external-LLM success/failure matrix. Final FastAPI runs as local
development with DEBUG off, rate limiting on and `SKILL_STORAGE_SHARED=false`;
an earlier true flag was not shared-volume proof. Local Ollama success, timeout,
connection-refusal, and malformed metadata job cases were verified on September
9, 2026. Failures retry and dead-letter without committing note metadata or
review memory. The migration batch is now `reconciled` through the formal
repository state machine. Local browser preflight also passed on September 9,
2026 (login, notes create/reload/list, cleanup, and SQL audit verification);
final user acceptance is still pending. This development single-instance run
is not production DNS/LB/TLS/shared-volume evidence.

Earlier diagnostic output exposed credentials. Target app, approval and JWT
signing secrets were rotated; the old app password is rejected. Only the E4
target container was rebound to its new environment, preserving volume/UUID.
A third-party API key still needs user/provider rotation; no secrets are included
in committed evidence. Prior checkpoints below are historical, not current gates.


This topology is dedicated to E4 business migration rehearsal. It defines
separate target and restore MySQL instances on loopback ports 33427 and 33428.
E1-E3 containers, volumes and networks are intentionally absent.

## Historical execution status: 2026-09-07

Real E4 operations are complete for the captured source snapshot, not the
application cutover. `e4_allowlist.json` now binds the exact source, target and
restore identities. A dedicated source account has SELECT/SHOW VIEW only;
target/restore app and root secrets are independent. The restore user is now
`doki_e4_restore`; its former `doki_e4_app` account is locked and revoked.
Only the two E4 containers were recreated, preserving volumes and server UUIDs.
E1-E3 resources and source business rows were not modified.

Both schemas have 39 tables at `20260905_0008_e4_business_shadow`.
Two canonical test users were rebuilt, 312 business records (including 62
necessary Skill input records) imported, and 314 mappings reconciled against
the captured bundle. The batch remains `imported`, not final-stage reconciled.
Repeat import produced 0 imported / 312 skipped, with no quarantine or FK
orphans. Four encrypted configs were actually decrypted using the existing
project key before binding an evidence-backed key version.

The final independent restore matches all 39 table definitions and 2,407 rows,
including retained auth/audit/job smoke evidence after synthetic business cleanup. Backup SHA-256:
`841b40167d79ee9c6ef940bd26af8db7fdc3b27474846dcdb23eff8b99a03e95`.
See `project_changes/2026-09-02-e4-ar3-business-migration/artifacts/e4-write-authority-20260907.json`
(relative to repository root) for redacted resource and evidence references.

Local-only secrets and backups are under repository-root `.runtime/e4/`,
Git-ignored and restricted to the owner/SYSTEM. Credential references map to
`live-credentials.json`; target test logins are in `test-users-login.json`.
Do not print or commit their contents. The private execution helper can safely
recheck business/source data and perform a fresh target-to-restore rehearsal:

```powershell
# Run from the repository root with the existing Windows virtual environment.
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py verify
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py source-recheck
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py restore
```

`restore` replaces the allowlisted restore schema contents after backing up
both servers; never redirect it to source or E1-E3. It issues fresh preflight
evidence and compares each table's DDL and row digest. Do not repeat bootstrap,
run a populated downgrade, or reuse an expired preflight file.

`scripts/e4_preflight.py` remains an identity-only gate, not a replacement for
schema, grants, backups or final stop-write checks. `scripts/e4_import.py`
checks business adapters, required payloads, timestamps, encryption key-version
metadata and document/media bytes before target access; offline success alone
does not prove ownership, actual decryption or restore safety.

## Daily business write authority

In explicitly guarded E4 runtime, `BusinessSession` assigns canonical
owner/entity/parent identities and content/key-version metadata, rejects
ownership changes and untracked bulk/raw writes, and commits business rows,
audit and durable jobs atomically. Request commits precede successful responses.
Chat parent creation and its paired messages share one UoW.

Knowledge uploads persist original bytes and jobs without synchronous Chroma;
streaming `accepted` is emitted only after SQL commit. Embedding switches queue
rebuilds. Owner-scoped `GET /jobs` and `GET /jobs/{job_id}` expose durable state.
Automatic/manual note enrichment uses the guarded E4 runner: a current lease
and fencing token are required, and note/memory changes and job completion
share one transaction. E2 and E4 runners cannot run simultaneously.

The default E4 runner registers note enrichment only. `e4.note.project`,
`e4.knowledge.project` and `e4.embedding.rebuild` await E5 generation-aware
workers and remain queued rather than consuming retries or reporting success.
No Chroma generation is activated. Existing Skill SQL mutations are audited
and run bindings validated; package/storage publication remains E6 scope.

E4 HTTP legacy tools/MCP, MD5 and reranker mutation endpoints return 410.
Django user/file/admin routes are rejected before views, and its database
router refuses ordinary ORM writes and migrations. The legacy key rotation
script refuses `--apply` in E4 mode. These are code safeguards: running old
processes have not been restarted and direct legacy database clients have not
had their write privileges globally revoked.

All 488 backend tests, Ruff and compileall pass. The private helper
`.runtime/e4/business_write_smoke.py` tested real authentication, business
routes, SQL state, rollback, accepted SSE and automatic/manual enrichment on
the allowlisted MySQL target, without Chroma/Redis or an external LLM. It uses
a deterministic tagger in a minimal FastAPI app, not the full `main` lifespan.
Synthetic entities were removed through audited transactions; two of nine new
jobs succeeded and the remaining seven were explicitly cancelled after
cleanup. Audit/job evidence and previous backups remain. Django's own runtime
also refused all 14 legacy route probes without calling views or a database.

The missing test PDF is explicitly excluded with user approval and SQL audit
`migration.source_excluded`; see the redacted `e4-pdf-exclusion-20260907.json`
artifact. It no longer blocks migration. Its historical sidecar/chunks and
other originals are untouched; this is not a general cleanup authorization.

**Unfinished as of September 7 (superseded above):** final source stop-write/freeze, old-process deployment
and traffic/DSN cutover, full application lifecycle and complete business/
Redis-failure matrix. Application `.env`/permanent DSN is unchanged. Real
runner kill/restart, lease recovery, process-lock exclusion and stale fencing
tests pass, but do not substitute for the full application gate. Final user
acceptance has not happened; E4 is not closed.

## Initialization template and historical observations

The target database is `doki_e4` on `127.0.0.1:33427`; the independent
restore database uses the same schema name on `127.0.0.1:33428`. Set separate
local-only credentials before first creation; never commit or paste them into
logs. The following is an initialization template, not a command to rerun
against an existing E4 topology:

```powershell
$env:E4_TARGET_MYSQL_ROOT_PASSWORD = '<local-only-target-root-password>'
$env:E4_TARGET_MYSQL_PASSWORD = '<local-only-target-app-password>'
$env:E4_RESTORE_MYSQL_ROOT_PASSWORD = '<local-only-restore-root-password>'
$env:E4_RESTORE_MYSQL_PASSWORD = '<local-only-restore-app-password>'
docker compose up -d
docker compose ps
```

The September 3 handoff and September 5 exited-container observations are
historical artifacts. They are superseded by the September 7 execution
checkpoint, not deleted. Container IDs changed during the authorized credential
separation; the current allowlist, not an old inspection, is authoritative.
Do not rerun the initialization template against the populated E4 topology.

Preflight purposes are role-bound: source permits inventory, snapshot, backup,
dry-run, and validate; target permits inventory, snapshot, backup, dry-run,
migrate, switch, runtime, and validate; restore permits inventory, restore,
restore-forward, and validate. A container-backed target also requires a fresh,
independent container inspection when a preflight is issued or consumed. During
issuance, the container facts are validated against the allowlist before the
database inspector is allowed to connect. The issuance switch, purpose/role,
migration switch, approval token and lifetime are also validated before either
injected inspector is invoked. A consumed preflight is checked for static
validity before a live container reinspection. `load_guard_from_config` does
not accept recorded or caller-supplied container facts as a substitute for the
inspector; static facts remain available only to the pure record builder and
validator used by offline tests and issuance internals.
