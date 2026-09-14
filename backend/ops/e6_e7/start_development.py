"""Start the full Doki development app against the pinned local SQL target."""

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from dotenv import dotenv_values

    from ops.e6_e7.acceptance_env import save
    from ops.e6_e7.target_env import target_environment

    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--enable-runner", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / ".runtime"):
        raise ValueError("Keep runtime evidence in workspace")
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "processes.json").exists():
        raise ValueError("Use a fresh invocation directory")
    for port in (18000, 18080):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise ValueError(f"Doki port {port} is occupied; do not replace existing processes")
    env = dict(os.environ)
    env.update({key: value for key, value in dotenv_values(ROOT / "backend/.env").items() if value is not None})
    env.update(target_environment(directory))
    env.update(
        ENV="dev", DEBUG_MODE="false", RATE_LIMIT_ENABLED="true",
        REDIS_HOST="127.0.0.1", REDIS_PORT="18020", REDIS_DB="3",
        AUTH_JWT_SECRET=json.loads((ROOT / ".runtime/e4/runtime-auth-secret.json").read_text(encoding="utf-8"))["AUTH_JWT_SECRET"],
        CORS_ALLOWED_ORIGINS="http://127.0.0.1:18080,http://localhost:18080",
        LLM_TYPE="OLLAMA", OLLAMA_MODEL_NAME="qwen3:0.6b", EMBED_MODEL_TYPE="OLLAMA",
        SKILL_STORAGE_DIR=str(ROOT / "backend/data/skill_packages"), SKILL_STORAGE_SHARED="true",
        E4_RUNNER_ENABLED=str(args.enable_runner).lower(),
    )
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    processes = {}
    for name, command, cwd, child_env in [
        ("backend", [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "18000", "--no-access-log"],
         ROOT / "backend", env),
        ("frontend", ["C:/nvm4w/nodejs/node.exe", str(ROOT / "front/node_modules/vite/bin/vite.js"),
                      "--host", "127.0.0.1", "--port", "18080", "--strictPort"],
         ROOT / "front", dict(os.environ, VITE_BACKEND_TARGET="http://127.0.0.1:18000")),
    ]:
        with (directory / f"{name}.out.log").open("xb") as out, (directory / f"{name}.err.log").open("xb") as err:
            process = subprocess.Popen(command, cwd=cwd, env=child_env, stdout=out, stderr=err, creationflags=creationflags)
        processes[name] = {"pid": process.pid, "command": command, "cwd": str(cwd)}
    save(directory / "processes.json", processes)
    print(json.dumps({"pids": {name: value["pid"] for name, value in processes.items()}, "url": "http://127.0.0.1:18080"}))


if __name__ == "__main__":
    main()
