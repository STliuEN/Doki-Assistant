"""Fresh E6/E7 invocation for the explicitly authorized local Doki target."""

import os
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from ops.e5.verify_closure import ROOT, TARGET, TARGET_UUID, inspect_container, prepare, sha_file
from ops.e6_e7.acceptance_env import save


def target_environment(directory: Path, *, purposes=("runtime",)) -> dict[str, str]:
    directory = directory.resolve()
    if not directory.is_relative_to(ROOT / ".runtime"):
        raise ValueError("Invocation evidence must stay in workspace .runtime")
    directory.mkdir(parents=True, exist_ok=True)
    prepare()  # Checks exact original ID, loopback address and port; no SQL writes.
    container = inspect_container(TARGET)
    invocation = uuid4().hex
    allowlist = directory / f"allowlist-{invocation}.json"
    preflight = directory / f"preflight-{invocation}.json"
    save(allowlist, {"schema_version": 1, "stage": "E6E7", "targets": [{
        "id": "e6e7-doki-target", "role": "target", "host": "127.0.0.1", "port": 33427,
        "database": "doki_e4", "server_uuid": TARGET_UUID, "credential_ref": "e6e7-doki-app",
        "database_username": "doki_e4_app", "read_only": False,
        "container_name": TARGET, "container_id": container["Id"],
        "image_reference": container["Config"]["Image"], "image_id": container["Image"],
        "network": "doki-e4-20260903-net",
    }]})
    env = dict(os.environ, E4_MIGRATION_ENABLED="I_UNDERSTAND_E4_MIGRATION", E6E7_ENABLED="true",
               E4_ALLOWLIST_FILE=str(allowlist), E4_TARGET_ID="e6e7-doki-target",
               E4_CREDENTIAL_REF="e6e7-doki-app", E4_APPROVAL_TOKEN=secrets.token_hex(24),
               E4_PREFLIGHT_FILE=str(preflight), E4_RUNNER_ENABLED="false", ENV="dev")
    issued = subprocess.run([
        sys.executable, str(ROOT / "backend/scripts/e4_preflight.py"), "--output", str(preflight),
        "--purposes", *purposes, "--issuance-switch", "I_UNDERSTAND_E4_PREFLIGHT_ISSUANCE",
    ], env=env, capture_output=True)
    if issued.returncode:
        raise RuntimeError("Fresh E6/E7 target preflight failed")
    save(directory / f"invocation-{invocation}.private.json", {"approval_token": env["E4_APPROVAL_TOKEN"]})
    save(directory / f"invocation-{invocation}.json", {
        "stage": "E6E7", "purposes": list(purposes), "preflight_sha256": sha_file(preflight),
        "allowlist_sha256": sha_file(allowlist),
    })
    return env
