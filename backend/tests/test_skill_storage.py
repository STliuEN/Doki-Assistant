import base64
import zipfile
from io import BytesIO

import pytest

from app.skills.package import SkillPackageError
from app.skills.storage import (
    SkillPackageStorage,
    build_skill_archive,
    render_skill_markdown,
    validate_skill_storage_configuration,
)


def _archive(*, body: str = "Use the reference.", extra: dict[str, bytes] | None = None) -> bytes:
    files = {
        "SKILL.md": render_skill_markdown(
            name="portable-skill",
            description="A portable test skill.",
            instructions=body,
            frontmatter={"unknown-field": {"preserve": True}},
        ),
        **(extra or {}),
    }
    return build_skill_archive(files)


def test_storage_normalizes_and_deduplicates_by_content(tmp_path) -> None:
    storage = SkillPackageStorage(tmp_path)

    first = storage.store_archive(_archive(extra={"references/guide.md": b"guide"}))
    second = storage.store_archive(_archive(extra={"references/guide.md": b"guide"}))

    assert first.digest == second.digest
    assert first.storage_key == second.storage_key
    assert storage.read_resource(first.storage_key, "references/guide.md") == b"guide"
    assert (tmp_path / first.storage_key).is_file()
    assert not list((tmp_path / "staging").iterdir())


def test_storage_export_is_a_portable_standard_package(tmp_path) -> None:
    storage = SkillPackageStorage(tmp_path)
    stored = storage.store_archive(_archive())

    with zipfile.ZipFile(BytesIO(storage.read_archive(stored.storage_key))) as archive:
        assert sorted(archive.namelist()) == ["SKILL.md"]
        skill_markdown = archive.read("SKILL.md").decode("utf-8")

    assert "name: portable-skill" in skill_markdown
    assert "unknown-field:" in skill_markdown
    assert "skill.yaml" not in skill_markdown


def test_storage_never_exposes_arbitrary_paths(tmp_path) -> None:
    storage = SkillPackageStorage(tmp_path)

    with pytest.raises(SkillPackageError, match="storage_key"):
        storage.read_archive("../../outside.zip")


def test_storage_quarantines_and_repairs_valid_zip_tampering_at_a_content_addressed_key(tmp_path) -> None:
    storage = SkillPackageStorage(tmp_path)
    stored = storage.store_archive(_archive(body="Original."))
    object_path = tmp_path / stored.storage_key
    tampered = _archive(body="Tampered but still a valid Skill ZIP.")
    object_path.write_bytes(tampered)

    for operation in (
        lambda: storage.load_archive(stored.storage_key, expected_digest=stored.digest),
        lambda: storage.read_archive(stored.storage_key, expected_digest=stored.digest),
    ):
        with pytest.raises(SkillPackageError) as error:
            operation()
        assert error.value.code == "storage_digest_mismatch"

    repaired = storage.store_archive(_archive(body="Original."))
    assert repaired.digest == stored.digest
    assert storage.read_archive(stored.storage_key, expected_digest=stored.digest) != tampered
    quarantined = list((tmp_path / "quarantine").glob(f"{stored.digest}-*.zip"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == tampered


def test_storage_rejects_database_digest_that_disagrees_with_the_key(tmp_path) -> None:
    storage = SkillPackageStorage(tmp_path)
    stored = storage.store_archive(_archive())

    with pytest.raises(SkillPackageError) as error:
        storage.read_archive(stored.storage_key, expected_digest="f" * 64)

    assert error.value.code == "storage_digest_mismatch"


@pytest.mark.parametrize(
    "environment,multi_instance",
    [("production", False), ("development", True)],
)
def test_shared_storage_is_mandatory_in_production_or_multi_instance(
    tmp_path,
    monkeypatch,
    environment: str,
    multi_instance: bool,
) -> None:
    monkeypatch.delenv("SKILL_STORAGE_DIR", raising=False)
    monkeypatch.delenv("SKILL_STORAGE_SHARED", raising=False)
    monkeypatch.setenv("SKILL_MULTI_INSTANCE", str(multi_instance).lower())

    with pytest.raises(RuntimeError, match="shared durable volume"):
        validate_skill_storage_configuration(
            environment,
            storage=SkillPackageStorage(tmp_path / "local"),
        )


def test_explicit_shared_filesystem_contract_and_health_probe(tmp_path, monkeypatch) -> None:
    root = (tmp_path / "shared-volume").resolve()
    storage = SkillPackageStorage(root)
    monkeypatch.setenv("SKILL_STORAGE_BACKEND", "filesystem")
    monkeypatch.setenv("SKILL_STORAGE_DIR", str(root))
    monkeypatch.setenv("SKILL_STORAGE_SHARED", "true")
    monkeypatch.setenv("SKILL_MULTI_INSTANCE", "true")

    validate_skill_storage_configuration("production", storage=storage)

    assert storage.check_health()


def test_editor_resource_input_can_round_trip_binary_data(tmp_path) -> None:
    content = b"\x00\x01asset"
    encoded = base64.b64encode(content).decode("ascii")
    assert base64.b64decode(encoded, validate=True) == content

    storage = SkillPackageStorage(tmp_path)
    stored = storage.store_files({"SKILL.md": _archive()[:0] + render_skill_markdown(
        name="asset-skill",
        description="Uses a binary asset.",
        instructions="Read the asset.",
    ), "assets/data.bin": content})
    assert storage.read_resource(stored.storage_key, "assets/data.bin") == content
