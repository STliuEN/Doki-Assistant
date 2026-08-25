from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.failed_response_register import register_exception_handlers
from app.skills.service import SKILL_REGISTRY_STALE_MESSAGE, SkillRegistryStaleError


def test_registry_stale_error_is_globally_mapped_to_503() -> None:
    app = FastAPI()

    @app.get("/registry-dependent")
    async def registry_dependent() -> None:
        raise SkillRegistryStaleError("internal revision details")

    register_exception_handlers(app)
    with TestClient(app) as client:
        response = client.get("/registry-dependent")

    assert response.status_code == 503
    assert response.json() == {
        "code": 503,
        "message": SKILL_REGISTRY_STALE_MESSAGE,
        "data": None,
    }


def test_registry_dependent_routes_publish_503_in_openapi() -> None:
    from main import app

    schema = app.openapi()
    operations = [
        schema["paths"]["/skills/catalog"]["get"],
        schema["paths"]["/skills/{skill_id}/publish"]["post"],
        schema["paths"]["/chat/skills"]["get"],
        schema["paths"]["/chat/agent/query/stream"]["post"],
        schema["paths"]["/chat/session/{session_id}/messages/{message_id}/regenerate/stream"]["post"],
    ]

    for operation in operations:
        response = operation["responses"]["503"]
        assert response["description"] == SKILL_REGISTRY_STALE_MESSAGE
        assert "ApiResponse" in response["content"]["application/json"]["schema"]["$ref"]
