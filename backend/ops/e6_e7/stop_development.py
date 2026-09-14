"""Stop only processes recorded by the matching local Doki launcher."""

import argparse
import json
import os
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert directory.is_relative_to(ROOT / ".runtime")
    records = json.loads((directory / "processes.json").read_text(encoding="utf-8"))
    verified = []
    for name, record in records.items():
        if not psutil.pid_exists(record["pid"]):
            continue
        process = psutil.Process(record["pid"])
        actual = process.cmdline()
        assert actual[1:] == record["command"][1:], "PID command changed; do not stop it"
        assert Path(process.cwd()).resolve() == Path(record["cwd"]).resolve()
        children = process.children(recursive=True)
        for child in children:
            child_cwd = Path(child.cwd()).resolve()
            console_host = Path(os.environ["SystemRoot"]) / "System32/conhost.exe"
            assert child_cwd.is_relative_to(ROOT) or Path(child.exe()).resolve() == console_host.resolve(), "Unexpected Doki child process"
        verified.extend(reversed(children))
        verified.append(process)
    for process in verified:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(verified, timeout=15)
    assert not alive, "Doki processes did not stop; no unrelated process will be killed"
    print(json.dumps({"stopped_pids": [process.pid for process in verified]}))


if __name__ == "__main__":
    main()
