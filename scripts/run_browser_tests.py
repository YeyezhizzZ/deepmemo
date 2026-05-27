#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import socket
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"
PYTHON_BIN = REPO_ROOT / ".venv" / "bin" / "python3.11"
BACKEND_URL = "http://127.0.0.1:8000/"
FRONTEND_URL = "http://127.0.0.1:5173/"
SCENARIOS_PATH = APP_ROOT / "tests/browser/scenarios.yaml"
FIXTURES_ROOT = APP_ROOT / "tests/browser/fixtures"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def wait_for_url(url: str, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    while time.time() < deadline:
        try:
            with opener.open(url, timeout=2) as response:
                response.read()
            return
        except Exception as exc:  # pragma: no cover - best-effort readiness probe
            last_error = exc
            time.sleep(0.5)

    raise RuntimeError(f"Timed out waiting for {url}") from last_error


def spawn(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(command, cwd=cwd, env=env)


def terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def load_active_dataset() -> str:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as handle:
        scenarios = yaml.safe_load(handle)["scenarios"]

    active = [scenario for scenario in scenarios if scenario.get("status") == "active"]
    datasets = {scenario.get("dataset") for scenario in active if scenario.get("dataset")}
    if not datasets:
        raise RuntimeError("No active browser scenarios were found in app/tests/browser/scenarios.yaml")
    if len(datasets) > 1:
        raise RuntimeError(f"Active browser scenarios must share one dataset for now: {sorted(datasets)}")
    return next(iter(datasets))


def prepare_workspace(dataset: str) -> tuple[Path, Path]:
    fixture_data = FIXTURES_ROOT / dataset / "data"
    if not fixture_data.exists():
        raise RuntimeError(f"Browser fixture dataset not found: {fixture_data}")

    workspace_root = Path(tempfile.mkdtemp(prefix="deepmemo-browser-"))
    data_dir = workspace_root / "data"
    shutil.copytree(fixture_data, data_dir)
    db_path = workspace_root / "data.db"

    os.environ["DEEPMEMO_DATA_DIR"] = str(data_dir)
    os.environ["DEEPMEMO_DB_PATH"] = str(db_path)

    from src.app.database import init_db

    init_db()
    return data_dir, db_path


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    python_bin = PYTHON_BIN if PYTHON_BIN.exists() else Path(sys.executable)
    dataset = load_active_dataset()
    data_dir, db_path = prepare_workspace(dataset)
    backend_port = pick_free_port()
    frontend_port = pick_free_port()
    backend_url = f"http://127.0.0.1:{backend_port}/"
    frontend_url = f"http://127.0.0.1:{frontend_port}/"

    backend_env = os.environ.copy()
    backend_env.update(
        {
            "DEEPMEMO_DATA_DIR": str(data_dir),
            "DEEPMEMO_DB_PATH": str(db_path),
            "DEEPMEMO_WATCHER_MODE": "polling",
            "DEEPMEMO_BASE_URL": frontend_url,
            "PYTHONPATH": str(REPO_ROOT),
            "UV_CACHE_DIR": "/private/tmp/deepmemo-uv-cache",
        }
    )

    frontend_env = os.environ.copy()
    frontend_env.update(
        {
            "DEEPMEMO_API_PROXY_TARGET": backend_url,
            "DEEPMEMO_BASE_URL": frontend_url,
        }
    )
    playwright_env = os.environ.copy()
    playwright_env.update({"DEEPMEMO_BASE_URL": frontend_url})

    backend = spawn(
        [
            str(python_bin),
            "-m",
            "uvicorn",
            "src.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(backend_port),
        ],
        cwd=REPO_ROOT,
        env=backend_env,
    )
    frontend = spawn(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port)],
        cwd=APP_ROOT,
        env=frontend_env,
    )

    try:
        wait_for_url(backend_url)
        wait_for_url(frontend_url)
        completed = subprocess.run(["npm", "run", "test:browser:run"], cwd=APP_ROOT, env=playwright_env)
        return completed.returncode
    finally:
        terminate(frontend)
        terminate(backend)


if __name__ == "__main__":
    raise SystemExit(main())
