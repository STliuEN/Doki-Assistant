"""Additive schema rehearsal limited to a new E6/E7 replica."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from ops.e6_e7.acceptance_env import preflight, save, sql
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    env = preflight(directory, ("migrate", "runtime", "validate"))
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=ROOT / "backend", env=env, capture_output=True)
    (directory / "schema-upgrade.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Replica schema upgrade failed; inspect private schema-upgrade.log")
    private = json.loads((directory / "credentials.private.json").read_text(encoding="utf-8"))
    revision = sql(private["container"], private["password"], "SELECT version_num FROM alembic_version",
                   private["username"], "doki_e4")
    assert revision == "20260914_0010_e6e7_sql_authority"
    save(directory / "schema-upgrade.json", {"status": "passed", "revision": revision})
    print(json.dumps({"status": "passed", "revision": revision}))


if __name__ == "__main__":
    main()
