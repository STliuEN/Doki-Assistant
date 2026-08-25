from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
LEGACY_SKILL_SOURCE = APP_ROOT / "agent" / "skills"
FORBIDDEN_RUNTIME_TOKENS = (
    "skill.yaml",
    "skills_dir",
    "legacy_skills_dir",
    "app/agent/skills",
)


def test_legacy_skill_source_tree_is_absent() -> None:
    assert not LEGACY_SKILL_SOURCE.exists()
    assert not list(APP_ROOT.rglob("skill.yaml"))


def test_runtime_cannot_reintroduce_legacy_skill_source_reads() -> None:
    offenders: dict[str, list[str]] = {}
    for source_path in APP_ROOT.rglob("*.py"):
        source = source_path.read_text(encoding="utf-8").replace("\\", "/").casefold()
        matches = [token for token in FORBIDDEN_RUNTIME_TOKENS if token in source]
        if matches:
            offenders[source_path.relative_to(BACKEND_ROOT).as_posix()] = matches

    assert offenders == {}
