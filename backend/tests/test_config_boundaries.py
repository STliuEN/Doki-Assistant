from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.mcp.config import load_mcp_servers, update_mcp_server_config
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


def test_security_config_path_and_environment_are_merged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    security_path = tmp_path / "security.yaml"
    security_path.write_text(
        "admin:\n  user_ids:\n    - config-user\n  usernames:\n    - config-admin\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SECURITY_CONFIG_PATH", str(security_path))
    monkeypatch.setenv("ADMIN_USER_IDS", "env-user")
    monkeypatch.setenv("ADMIN_USERNAMES", "env-admin")

    user_ids, usernames = auth_utils._read_security_admins()

    assert user_ids == {"config-user", "env-user"}
    assert usernames == {"config-admin", "env-admin"}


def test_production_rejects_placeholder_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "replace-with-shared-django-jwt-secret")
    monkeypatch.setenv("MODEL_CONFIG_ENCRYPTION_KEY", "short")

    with pytest.raises(RuntimeError, match="Invalid security configuration"):
        auth_utils.validate_security_configuration()


def test_production_accepts_distinct_strong_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "jwt-" + "a" * 40)
    monkeypatch.setenv("MODEL_CONFIG_ENCRYPTION_KEY", "model-" + "b" * 40)

    auth_utils.validate_security_configuration()


def test_production_rejects_reused_encryption_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    reused = "shared-" + "c" * 40
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", reused)
    monkeypatch.setenv("MODEL_CONFIG_ENCRYPTION_KEY", reused)

    with pytest.raises(RuntimeError, match="must be different"):
        auth_utils.validate_security_configuration()


def test_mcp_example_servers_are_disabled() -> None:
    config_path = Path(__file__).parents[1] / "app" / "config" / "mcp.example.yaml"

    servers = load_mcp_servers(config_path)

    assert servers
    assert all(not server.enabled for server in servers)


def test_mcp_updates_explicit_writable_config(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.local.yaml"
    config_path.write_text(
        "servers:\n"
        "  - id: sample\n"
        "    label: Sample\n"
        "    enabled: false\n",
        encoding="utf-8",
    )

    update_mcp_server_config("sample", {"enabled": True}, config_path)

    servers = load_mcp_servers(config_path)
    assert len(servers) == 1
    assert servers[0].enabled is True
