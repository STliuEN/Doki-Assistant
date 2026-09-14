import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.router import health


@pytest.mark.parametrize("sql_ready", [True, False])
def test_sql_health_has_no_filesystem_dependency(monkeypatch, sql_ready):
    monkeypatch.setenv("E6E7_ENABLED", "true")
    monkeypatch.setenv("E5_RAG_ENABLED", "true")
    monkeypatch.setattr(health, "check_mysql_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "check_redis_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "sql_skill_storage_ready", AsyncMock(return_value=sql_ready))

    def forbidden_disk_probe():
        raise AssertionError("SQL runtime must not depend on the legacy filesystem")

    monkeypatch.setattr(health.skill_package_storage, "check_health", forbidden_disk_probe)
    if sql_ready:
        response = asyncio.run(health.get_health_readiness())
        assert response.data["status"] == "ok"
        assert response.data["dependencies"]["chroma_projection"]["status"] == "owner_scoped"
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(health.get_health_readiness())
        assert error.value.status_code == 503
