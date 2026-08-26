from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.router import skill_router as router_module
from app.skills.package import SkillPackageError
from app.skills.service import SkillConflictError


def _upload(content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename="fixture.zip",
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


def test_import_route_rejects_non_zip_media_type_before_service(monkeypatch) -> None:
    called = False

    async def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(router_module.skill_service, "import_archive", fail_if_called)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router_module.import_skill_package(
                file=_upload(b"not-a-zip", "text/plain; charset=utf-8"),
                idempotency_key="media-type",
                actor_id="admin",
                db=object(),
            )
        )

    assert error.value.status_code == 415
    assert called is False


def test_import_route_rejects_oversized_archive_before_service(monkeypatch) -> None:
    called = False

    async def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    fake_service = SimpleNamespace(
        storage=SimpleNamespace(limits=SimpleNamespace(max_archive_bytes=3)),
        import_archive=fail_if_called,
    )
    monkeypatch.setattr(router_module, "skill_service", fake_service)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router_module.import_skill_package(
                file=_upload(b"1234", "application/zip"),
                idempotency_key="too-large",
                actor_id="admin",
                db=object(),
            )
        )

    assert error.value.status_code == 413
    assert called is False


def test_import_route_maps_idempotency_conflict_to_409(monkeypatch) -> None:
    async def conflict(*args, **kwargs):
        raise SkillConflictError("Idempotency-Key is already bound")

    fake_service = SimpleNamespace(
        storage=SimpleNamespace(limits=SimpleNamespace(max_archive_bytes=32)),
        import_archive=conflict,
    )
    monkeypatch.setattr(router_module, "skill_service", fake_service)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router_module.import_skill_package(
                file=_upload(b"1234", "application/zip"),
                idempotency_key="duplicate",
                actor_id="admin",
                db=object(),
            )
        )

    assert error.value.status_code == 409


def test_service_storage_unavailable_maps_to_stable_503() -> None:
    with pytest.raises(HTTPException) as error:
        router_module._raise_service_error(
            SkillPackageError("storage_unavailable", "storage volume is read-only")
        )

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "storage_unavailable"
