"""Run the web app and API against the ISOLATED acceptance database, loopback only.

Companion to ``backend/scripts/seed_acceptance.py``. It never reads or writes the development
database: both DSNs are derived from the configured ones with the database name swapped for the
test database (``touche_commerce_test``), exactly like the integration tests do. Nothing is
bound to a non-loopback address.

    python scripts/acceptance_stack.py            # first free ports from 3020 / 8020
    python scripts/acceptance_stack.py --web-port 3020 --api-port 8020

It prints the two URLs, writes ``backend/var/acceptance/stack.json`` (ports and process ids)
so test runners can find the stack, and stops both servers on Ctrl+C or when terminated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"
STATE = BACKEND / "var" / "acceptance" / "stack.json"
LOG_DIR = BACKEND / "var" / "acceptance"

sys.path.insert(0, str(BACKEND))


def _free_port(start: int) -> int:
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit(f"No free port found from {start}.")


def _backend_python() -> str:
    for candidate in (
        BACKEND / ".venv" / "Scripts" / "python.exe",
        BACKEND / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _wait(url: str, seconds: int, name: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - loopback
                if response.status < 500:
                    return
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(1)
    raise SystemExit(f"{name} did not become healthy at {url} within {seconds}s.")


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        taskkill = shutil.which("taskkill") or "taskkill.exe"
        subprocess.run(  # noqa: S603 - own child process only
            [taskkill, "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web-port", type=int, default=0)
    parser.add_argument("--api-port", type=int, default=0)
    args = parser.parse_args()

    from app.core.config import Settings

    settings = Settings()
    runtime_dsn = settings.test_database_dsn
    migration_dsn = settings.test_migration_dsn
    if runtime_dsn is None or migration_dsn is None:
        raise SystemExit("No database DSN configured; cannot derive the isolated test database.")
    if not runtime_dsn.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
        raise SystemExit("Refusing to start: the derived database is not a *_test database.")

    api_port = args.api_port or _free_port(8020)
    web_port = args.web_port or _free_port(3020)
    web_origin = f"http://localhost:{web_port}"
    api_origin = f"http://127.0.0.1:{api_port}"

    env = {
        **os.environ,
        "TOUCHE_ENVIRONMENT": "local",
        "TOUCHE_DATABASE_URL": runtime_dsn,
        "TOUCHE_DATABASE_MIGRATION_URL": migration_dsn,
        "TOUCHE_CORS_ALLOWED_ORIGINS": json.dumps([web_origin, f"http://127.0.0.1:{web_port}"]),
        "NEXT_PUBLIC_API_BASE_URL": api_origin,
        "API_INTERNAL_BASE_URL": api_origin,
        "NEXT_TELEMETRY_DISABLED": "1",
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm was not found on PATH.")

    processes: list[subprocess.Popen[bytes]] = []

    def stop(*_: object) -> None:
        for process in reversed(processes):
            _kill_tree(process)
        STATE.unlink(missing_ok=True)

    signal.signal(signal.SIGINT, lambda *_: (stop(), sys.exit(130)))
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: (stop(), sys.exit(130)))
    signal.signal(signal.SIGTERM, lambda *_: (stop(), sys.exit(143)))

    try:
        with (
            (LOG_DIR / "api.log").open("wb") as api_log,
            (LOG_DIR / "web.log").open("wb") as web_log,
        ):
            api = subprocess.Popen(  # noqa: S603 - fixed local command
                [
                    _backend_python(),
                    "-m",
                    "uvicorn",
                    "app.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                    "--proxy-headers",
                    "--no-server-header",
                ],
                cwd=BACKEND,
                env=env,
                stdout=api_log,
                stderr=subprocess.STDOUT,
            )
            processes.append(api)
            _wait(f"{api_origin}/api/v1/health/live", 60, "API")

            web = subprocess.Popen(  # noqa: S603 - fixed local command
                [npm, "run", "dev", "--", "--port", str(web_port)],
                cwd=FRONTEND,
                env=env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
            )
            processes.append(web)
            _wait(f"{web_origin}/login", 180, "Web app")

            STATE.write_text(
                json.dumps(
                    {
                        "web": web_origin,
                        "api": api_origin,
                        "database": "touche_commerce_test",
                        "pids": [p.pid for p in processes],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"Acceptance stack is up: web {web_origin}  api {api_origin}", flush=True)
            print("Database: isolated test database. Press Ctrl+C to stop.", flush=True)
            while all(p.poll() is None for p in processes):
                time.sleep(1)
            print("A server exited; stopping the stack.", flush=True)
            return 1
    finally:
        stop()


if __name__ == "__main__":
    raise SystemExit(main())
