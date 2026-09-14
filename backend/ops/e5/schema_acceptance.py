"""Empty and populated schema upgrades in two fresh databases of the E5 replica."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import docker, environment, preflight, save, sql  # noqa: E402 - standalone CLI backend path bootstrap


def main(directory):
    directory = directory.resolve()
    environment(directory)  # Exact container + loopback port; rejects original target/3306.
    private = json.loads((directory / "credentials.private.json").read_text())
    original = ROOT / ".runtime/e4/backup-target-bbcf14de7d4024aa.sql"
    content = original.read_bytes()
    assert hashlib.sha256(content).hexdigest().startswith("bbcf14de7d4024aa")
    assert b"20260905_0008_e4_business_shadow" in content and not re.search(rb"(?im)^\s*(USE |CREATE DATABASE)", content)
    reports = []
    for database, populated in (("e5_empty", False), ("e5_populated", True)):
        path = directory / database
        path.mkdir(exist_ok=False)
        assert not sql(private["container"], private["root_password"], "SHOW DATABASES LIKE '" + database + "'")
        sql(
            private["container"],
            private["root_password"],
            "CREATE DATABASE " + database + " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; "
            "GRANT ALL ON " + database + ".* TO '" + private["username"] + "'@'%'",
        )
        target = json.loads((directory / "allowlist.json").read_text())
        target["targets"][0]["database"] = database
        save(path / "allowlist.json", target)
        save(path / "credentials.private.json", {**private, "database": database, "chroma": str(path / "chroma")})
        (path / "target-current.sql").write_bytes(content if populated else b"-- fresh empty E5 acceptance database\n")
        if populated:
            import os

            docker(
                "exec",
                "-i",
                "--env",
                "MYSQL_PWD",
                private["container"],
                "mysql",
                "-uroot",
                database,
                env=dict(os.environ, MYSQL_PWD=private["root_password"]),
                data=content,
            )
        tables = sql(
            private["container"],
            private["root_password"],
            "SELECT table_name FROM information_schema.tables WHERE table_schema='"
            + database
            + "' AND table_name <> 'alembic_version' ORDER BY table_name",
        ).splitlines()

        def data_digest():
            import os

            if not tables:
                return None
            data = docker(
                "exec",
                "--env",
                "MYSQL_PWD",
                private["container"],
                "mysqldump",
                "-u" + private["username"],
                "--single-transaction",
                "--skip-lock-tables",
                "--skip-add-locks",
                "--no-tablespaces",
                "--set-gtid-purged=OFF",
                "--hex-blob",
                "--skip-comments",
                "--skip-extended-insert",
                "--order-by-primary",
                "--no-create-info",
                database,
                *tables,
                env=dict(os.environ, MYSQL_PWD=private["password"]),
            )
            return hashlib.sha256(data).hexdigest()

        before = data_digest()
        env = preflight(path, ("migrate",))
        process = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=env, capture_output=True)
        (path / "migration.log").write_bytes(process.stdout + process.stderr)
        assert process.returncode == 0, "Upgrade failed; inspect replica migration log"
        after = data_digest()
        assert before == after
        revision = sql(private["container"], private["root_password"], "SELECT version_num FROM alembic_version", database=database)
        count = int(
            sql(
                private["container"], private["root_password"], "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='" + database + "'"
            )
        )
        assert revision == "20260914_0009_e5_rag_runtime" and count == 41
        reports.append(
            {
                "database": database,
                "populated": populated,
                "revision": revision,
                "table_count": count,
                "existing_data_before": before,
                "existing_data_after": after,
                "passed": True,
            }
        )
    save(directory / "schema-upgrades.json", {"passed": True, "cases": reports, "pre_e5_dump_sha256": hashlib.sha256(content).hexdigest()})
    print(json.dumps({"passed": True, "upgrades": len(reports)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    main(parser.parse_args().directory)
