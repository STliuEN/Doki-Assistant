import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import e4_guard
from scripts import e4_preflight


@pytest.fixture
def preflight_case(monkeypatch, tmp_path):
    for name in e4_guard.E4_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)
    targets = []
    for index, role in enumerate(("source", "target", "restore")):
        target = {
            "id": role,
            "role": role,
            "host": "127.0.0.1",
            "port": 34100 + index,
            "database": f"e4_{role}",
            "database_username": f"e4_{role}",
            "server_uuid": f"fixture-{role}",
            "credential_ref": f"fixture://{role}",
            "read_only": role == "source",
        }
        if role != "source":
            target.update(
                {
                    "container_name": f"doki-e4-fixture-{role}",
                    "container_id": f"fixture-container-{role}",
                    "image_reference": "mysql:8.4",
                    "image_id": "sha256:fixture-image",
                    "network": "doki-e4-fixture-net",
                }
            )
        targets.append(target)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"schema_version": 1, "targets": targets}), encoding="utf-8")
    environment = {
        "E4_DATABASE_URL": "mysql+aiomysql://e4_target:fixture-password@127.0.0.1:34101/e4_target?charset=utf8mb4",
        "E4_ALLOWLIST_FILE": str(allowlist),
        "E4_CREDENTIAL_REF": "fixture://target",
        "E4_TARGET_ID": "target",
        "E4_MIGRATION_ENABLED": e4_guard.E4_MIGRATION_SWITCH,
        "E4_APPROVAL_TOKEN": "fixture-approval-token",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    case = SimpleNamespace(
        output=tmp_path / "preflight.json",
        allowlist=allowlist,
        environment=environment,
        events=[],
        identity=("e4_target", "fixture-target"),
        healthy=True,
    )
    case.arguments = ["--output", str(case.output), "--purposes", "migrate", "--issuance-switch", e4_guard.E4_PREFLIGHT_ISSUANCE_SWITCH]

    def inspect_container(target):
        case.events.append("container")
        return {
            "container_name": target.container_name,
            "container_id": target.container_id,
            "image_reference": target.image_reference,
            "image_id": target.image_id,
            "networks": [target.network],
            "host_ports": [target.port],
            "running": True,
            "healthy": case.healthy,
        }

    async def run_sync(function, target):
        def execute(statement):
            assert str(statement) == "SELECT DATABASE(), @@server_uuid"
            case.events.append("identity-query")
            return SimpleNamespace(one=lambda: case.identity)

        return function(SimpleNamespace(execute=execute), target)

    @asynccontextmanager
    async def connection():
        case.events.append("connect")
        yield SimpleNamespace(run_sync=run_sync)

    async def dispose():
        case.events.append("dispose")

    def create_engine(database_url, **options):
        assert database_url == environment["E4_DATABASE_URL"]
        assert options["hide_parameters"] is True and options["echo"] is False
        assert options["connect_args"]["connect_timeout"] == 10
        case.events.append("engine")
        return SimpleNamespace(connect=connection, dispose=dispose)

    monkeypatch.setattr(e4_guard, "inspect_e4_container", inspect_container)
    monkeypatch.setattr(e4_preflight, "create_async_engine", create_engine)
    return case


def test_preflight_issues_consumable_record_after_container_and_identity_checks(preflight_case, capsys):
    case = preflight_case
    assert e4_preflight.main(case.arguments) == 0
    output = capsys.readouterr().out
    record_text = case.output.read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert case.events == ["container", "engine", "connect", "identity-query", "dispose"]
    assert json.loads(output)["scope"] == "resource-identity-only"
    for secret in ("fixture-password", "fixture-approval-token", case.environment["E4_DATABASE_URL"]):
        assert secret not in output + record_text
    target = e4_guard.validate_preflight_record(
        record,
        database_url=case.environment["E4_DATABASE_URL"],
        allowlist=case.allowlist,
        credential_ref="fixture://target",
        target_id="target",
        purpose="migrate",
        approval_token="fixture-approval-token",
        migration_switch=e4_guard.E4_MIGRATION_SWITCH,
        container_facts=record["container"],
    )
    assert target.target_id == "target"


@pytest.mark.parametrize(
    "name", ["E4_DATABASE_URL", "E4_ALLOWLIST_FILE", "E4_CREDENTIAL_REF", "E4_TARGET_ID", "E4_APPROVAL_TOKEN", "E4_MIGRATION_ENABLED"]
)
def test_preflight_missing_input_never_inspects_or_connects(name, preflight_case, monkeypatch, capsys):
    monkeypatch.delenv(name)
    assert e4_preflight.main(preflight_case.arguments) == 2
    assert json.loads(capsys.readouterr().out)["blocked"] is True
    assert preflight_case.events == []
    assert not preflight_case.output.exists()


@pytest.mark.parametrize("failure", ["issuance", "ttl", "role", "allowlist", "output_exists", "output_parent"])
def test_preflight_invalid_inputs_fail_before_inspectors(failure, preflight_case, capsys):
    case = preflight_case
    arguments = list(case.arguments)
    if failure == "issuance":
        arguments[-1] = "disabled"
    elif failure == "ttl":
        arguments.extend(["--lifetime-seconds", "901"])
    elif failure == "role":
        arguments[arguments.index("migrate")] = "restore"
    elif failure == "allowlist":
        case.allowlist.write_text("{}", encoding="utf-8")
    elif failure == "output_exists":
        case.output.write_text("preserve-evidence", encoding="utf-8")
    else:
        arguments[1] = str(case.output.parent / "missing" / "preflight.json")
    assert e4_preflight.main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["blocked"] is True
    assert case.events == []
    if failure == "output_exists":
        assert case.output.read_text(encoding="utf-8") == "preserve-evidence"
    else:
        assert not case.output.exists()


def test_unhealthy_container_prevents_engine_creation(preflight_case, capsys):
    preflight_case.healthy = False
    assert e4_preflight.main(preflight_case.arguments) == 2
    assert preflight_case.events == ["container"]
    assert not preflight_case.output.exists()
    assert json.loads(capsys.readouterr().out)["blocked"] is True


def test_database_identity_drift_disposes_engine_without_record(preflight_case, capsys):
    preflight_case.identity = ("e4_target", "different-server")
    assert e4_preflight.main(preflight_case.arguments) == 2
    assert preflight_case.events[-1] == "dispose"
    assert not preflight_case.output.exists()
    assert json.loads(capsys.readouterr().out)["blocked"] is True


def test_driver_exception_cannot_expose_credentials(preflight_case, monkeypatch, capsys):
    def failed_engine(*args, **kwargs):
        raise RuntimeError(preflight_case.environment["E4_DATABASE_URL"] + " fixture-approval-token")

    monkeypatch.setattr(e4_preflight, "create_async_engine", failed_engine)
    assert e4_preflight.main(preflight_case.arguments) == 2
    output = capsys.readouterr()
    assert "fixture-password" not in output.out + output.err
    assert "fixture-approval-token" not in output.out + output.err
    assert not preflight_case.output.exists()


def test_direct_preflight_cli_does_not_load_dotenv(preflight_case, tmp_path):
    environment = {name: value for name, value in os.environ.items() if name not in e4_guard.E4_ENVIRONMENT_NAMES}
    (tmp_path / ".env").write_text("\n".join(f"{name}={value}" for name, value in preflight_case.environment.items()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "e4_preflight.py"
    result = subprocess.run(
        [sys.executable, str(script), *preflight_case.arguments], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["blocked"] is True
    assert not preflight_case.output.exists()
