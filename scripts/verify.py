#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(command: list[str], cwd: Path = REPO_ROOT) -> int:
    printable = " ".join(command)
    print(f"\n$ {printable}", flush=True)
    completed = subprocess.run(command, cwd=cwd)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DeepMemo regression checks.")
    parser.add_argument(
        "--mode",
        choices=("quick", "full"),
        default="quick",
        help="quick excludes e2e tests; full runs the whole pytest suite.",
    )
    args = parser.parse_args()

    pytest_command = [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"]
    if args.mode == "quick":
        pytest_command.extend(["-m", "not e2e"])

    checks = [
        (pytest_command, REPO_ROOT),
        (["npm", "run", "build"], REPO_ROOT / "app"),
    ]
    if args.mode == "full":
        checks.append((["npm", "run", "test:browser"], REPO_ROOT / "app"))

    for command, cwd in checks:
        returncode = run_command(command, cwd)
        if returncode != 0:
            return returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
