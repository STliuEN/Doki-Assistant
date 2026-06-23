from __future__ import annotations

import subprocess
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


mcp = FastMCP("Doki PowerShell LS Test")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_within_project(relative_path: str) -> Path:
    target = (PROJECT_ROOT / (relative_path or ".")).resolve()
    if target != PROJECT_ROOT and PROJECT_ROOT not in target.parents:
        raise ValueError("Path must stay inside the project root.")
    return target


@mcp.tool(
    description=(
        "List files in a project directory using PowerShell Get-ChildItem. "
        "This is a read-only smoke test tool; it does not accept arbitrary commands."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def list_project_files(relative_path: str = ".", limit: int = 50) -> str:
    target = _resolve_within_project(relative_path)
    if not target.exists():
        raise ValueError(f"Path does not exist: {relative_path}")
    if not target.is_dir():
        raise ValueError(f"Path is not a directory: {relative_path}")

    safe_limit = max(1, min(int(limit), 100))
    env = os.environ.copy()
    env["DOKI_LS_TARGET"] = str(target)
    env["DOKI_LS_LIMIT"] = str(safe_limit)
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            "$TargetPath = [Environment]::GetEnvironmentVariable('DOKI_LS_TARGET'); "
            "$ItemLimit = [int][Environment]::GetEnvironmentVariable('DOKI_LS_LIMIT'); "
            "Get-ChildItem -LiteralPath $TargetPath -Force "
            "| Select-Object -First $ItemLimit Name,Mode,Length,LastWriteTime "
            "| ConvertTo-Json -Compress"
        ),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PowerShell ls failed")
    return completed.stdout.strip() or "[]"


if __name__ == "__main__":
    mcp.run("stdio")
