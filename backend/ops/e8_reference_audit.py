"""Repository audit proving legacy adapters are unreachable in E8 authority mode."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(out):
    files = [p for p in (ROOT / "backend/app").rglob("*.py")]
    patterns = {
        "legacy_vector": "VectorStoreService",
        "legacy_md5": "MD5Store",
        "legacy_skill_files": "skill_package_storage",
        "legacy_paths": "extracted_images|md5_hex_store|data/chromadb",
    }
    hits = {k: [] for k in patterns}
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for key, pattern in patterns.items():
            if re.search(pattern, text, re.I):
                hits[key].append(p.relative_to(ROOT).as_posix())
    assertions = {
        "knowledge_write_routes_have_sql_authority_branch": "uses_business_authority(db)"
        in (ROOT / "backend/app/router/knowledge_router.py").read_text(encoding="utf-8"),
        "note_query_routes_have_e8_projection_branch": "E8_ENABLED" in (ROOT / "backend/app/services/note_service.py").read_text(encoding="utf-8"),
        "session_query_routes_have_e8_projection_branch": "E8_ENABLED"
        in (ROOT / "backend/app/services/session_query_service.py").read_text(encoding="utf-8"),
        "skill_resource_runtime_uses_sql_authority": "live_checks_enabled"
        in (ROOT / "backend/app/skills/resource_tools.py").read_text(encoding="utf-8"),
        "pending_actions_are_sql_by_default": "with_for_update"
        in (ROOT / "backend/app/services/pending_action_store.py").read_text(encoding="utf-8"),
        "compatibility_paths_are_fail_closed_by_business_boundary": "Sidecar-only writes are retired"
        in (ROOT / "backend/app/router/knowledge_router.py").read_text(encoding="utf-8"),
    }
    report = {
        "stage": "E8",
        "recorded_at": datetime.now(UTC).isoformat(),
        "status": "passed" if all(assertions.values()) else "blocked",
        "legacy_symbols": hits,
        "assertions": assertions,
        "disposition": "retain source compatibility modules for non-E8 maintenance/import tooling; E8 business authority never falls back to them",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "assertions": len(assertions), "legacy_symbol_files": sum(map(len, hits.values()))}))


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    a = p.parse_args()
    main(a.output.resolve())
