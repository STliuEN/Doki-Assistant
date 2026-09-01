from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent.mcp.config import (
    McpPolicyAuthorityUnavailable,
    McpServerConfig,
    load_mcp_servers,
    update_mcp_server_config,
)
from app.agent.mcp.provider import McpToolProvider
from app.core.environment import normalize_environment
from app.router.mcp_router import _server_status
from app.utils import auth_utils
from app.utils.crypto_utils import decrypt_text, encrypt_text


def test_crypto_requires_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MODEL_CONFIG_ENCRYPTION_KEY"):
        encrypt_text("secret")


def test_crypto_round_trip_and_strict_wrong_key() -> None:
    encrypted = encrypt_text("api-key", secret="current-key")

    assert decrypt_text(encrypted, secret="current-key", strict=True) == "api-key"
    with pytest.raises(ValueError, match="Unable to decrypt"):
        decrypt_text(encrypted, secret="wrong-key", strict=True)


def test_legacy_secret_key_fallback_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY", "legacy-key")

    with pytest.warns(FutureWarning, match="backward compatibility"):
        encrypted = encrypt_text("api-key")
    with pytest.warns(FutureWarning, match="backward compatibility"):
        assert decrypt_text(encrypted) == "api-key"


def test_production_rejects_placeholder_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("AUTH_JWT_SECRET", "replace-with-independent-e3-auth-secret")
    monkeypatch.setenv("MODEL_CONFIG_ENCRYPTION_KEY", "short")

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        auth_utils.validate_security_configuration()
    with pytest.raises(RuntimeError, match="Unsupported ENV"):
        normalize_environment("staging")


def test_production_accepts_distinct_strong_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("AUTH_JWT_SECRET", "jwt-" + "a" * 40)
    monkeypatch.setenv("MODEL_CONFIG_ENCRYPTION_KEY", "model-" + "b" * 40)

    auth_utils.validate_security_configuration()

    env = os.environ.copy()
    env.update({"ENV": "production", "DEBUG_MODE": "false"})
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.failed_response import DEBUG_MODE; assert DEBUG_MODE is False"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    env["DEBUG_MODE"] = "true"
    result = subprocess.run(
        [sys.executable, "-c", "import app.core.failed_response"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "DEBUG_MODE must be false in production" in result.stderr


def test_production_rejects_reused_encryption_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    reused = "shared-" + "c" * 40
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("AUTH_JWT_SECRET", reused)
    monkeypatch.setenv("MODEL_CONFIG_ENCRYPTION_KEY", reused)

    with pytest.raises(RuntimeError, match="must be different"):
        auth_utils.validate_security_configuration()


def test_development_requires_an_explicit_e3_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.setenv("SECRET_KEY", "legacy-django-key-that-cannot-authorize-e3")

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        auth_utils.validate_security_configuration()


def test_mcp_example_servers_are_disabled() -> None:
    config_path = Path(__file__).parents[1] / "app" / "config" / "mcp.example.yaml"

    servers = load_mcp_servers(config_path)

    assert servers
    assert all(not server.enabled for server in servers)


def test_mcp_local_yaml_writes_fail_closed_by_default(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "mcp.local.yaml"
    config_path.write_text(
        "servers:\n"
        "  - id: sample\n"
        "    label: Sample\n"
        "    enabled: false\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("MCP_ALLOW_LOCAL_CONFIG_WRITES", raising=False)
    monkeypatch.delenv("MCP_POLICY_AUTHORITY", raising=False)
    monkeypatch.delenv("MCP_POLICY_AUTHORITY_VERSION", raising=False)

    with pytest.raises(McpPolicyAuthorityUnavailable, match="YAML writes are disabled"):
        update_mcp_server_config("sample", {"enabled": True}, config_path)

    assert load_mcp_servers(config_path)[0].enabled is False


def test_explicit_adapter_maintenance_can_update_a_scoped_yaml(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "mcp.local.yaml"
    config_path.write_text(
        "servers:\n"
        "  - id: sample\n"
        "    label: Sample\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_ALLOW_LOCAL_CONFIG_WRITES", "true")
    update_mcp_server_config("sample", {"enabled": True}, config_path)

    servers = load_mcp_servers(config_path)
    assert len(servers) == 1
    assert servers[0].enabled is True


def test_mcp_runtime_policy_is_fail_closed_without_versioned_authority() -> None:
    async def scenario() -> None:
        provider = McpToolProvider()
        server = McpServerConfig(id="sample", label="Sample", enabled=True)

        assert await provider.discover_tools() == []
        with pytest.raises(McpPolicyAuthorityUnavailable, match="cannot authorize discovery"):
            await provider.list_tools(server)
        with pytest.raises(McpPolicyAuthorityUnavailable, match="cannot authorize tool execution"):
            await provider.call_tool("sample", "lookup", {})

    import asyncio

    asyncio.run(scenario())


def test_mcp_yaml_catalog_is_explicitly_non_executable_without_authority() -> None:
    server = McpServerConfig(id="sample", label="Sample", enabled=True)

    status = _server_status(server)

    assert status["status"] == "policy_unavailable"
    assert status["policy_authority"] == "unavailable"
    assert status["runtime_enabled"] is False
    # The adapter may retain the configured value for UI/editing purposes,
    # but it must never be interpreted as runtime authorization.
    assert status["enabled"] is True
