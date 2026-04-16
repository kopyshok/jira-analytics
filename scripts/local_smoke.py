"""Run a local backend + frontend smoke check.

The script is intentionally dependency-free so it can be used during onboarding:

    py -3.10 scripts/local_smoke.py

It applies migrations, starts missing dev servers, checks key URLs, and stops
only the processes it started itself.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"


@dataclass(frozen=True)
class UrlCheck:
    name: str
    url: str
    contains: str | None = None


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen[bytes]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Jira Analytics smoke checks.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for local dev servers.")
    parser.add_argument("--backend-port", type=int, default=8000, help="Backend port.")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Frontend port.")
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Do not run alembic upgrade head before starting the backend.",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Only check already running servers; fail if they are not available.",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="Startup timeout in seconds.")
    return parser.parse_args()


def get_text(url: str, timeout: float = 5.0) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "jira-analytics-smoke"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def is_ok(url: str) -> bool:
    try:
        status, _body = get_text(url, timeout=2.0)
    except (OSError, urllib.error.URLError):
        return False
    return status == 200


def run_command(command: Sequence[str], cwd: Path) -> None:
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def start_process(name: str, command: Sequence[str], cwd: Path) -> ManagedProcess:
    print(f"Starting {name}: {' '.join(command)}")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return ManagedProcess(name=name, process=process)


def wait_for(name: str, url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not requested yet"

    while time.monotonic() < deadline:
        try:
            status, body = get_text(url, timeout=2.0)
            if status == 200:
                print(f"OK {name}: {url}")
                return
            last_error = f"HTTP {status}: {body[:200]}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)

        time.sleep(1.0)

    raise RuntimeError(f"{name} did not become ready at {url}: {last_error}")


def check_url(check: UrlCheck) -> None:
    status, body = get_text(check.url)
    if status != 200:
        raise RuntimeError(f"{check.name} expected HTTP 200, got {status}: {body[:200]}")

    if check.contains is not None and check.contains not in body:
        raise RuntimeError(
            f"{check.name} response did not contain {check.contains!r}: {body[:200]}"
        )

    print(f"OK {check.name}: {check.url}")


def stop_processes(processes: Sequence[ManagedProcess]) -> None:
    for managed in reversed(processes):
        process = managed.process
        if process.poll() is not None:
            continue

        print(f"Stopping {managed.name}...")
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            continue

        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main() -> int:
    args = parse_args()
    backend_base = f"http://{args.host}:{args.backend_port}"
    frontend_base = f"http://{args.host}:{args.frontend_port}"
    managed_processes: list[ManagedProcess] = []

    try:
        (REPO_ROOT / "data").mkdir(exist_ok=True)
        (REPO_ROOT / "exports").mkdir(exist_ok=True)

        if not args.skip_migrate:
            run_command([sys.executable, "-m", "alembic", "upgrade", "head"], REPO_ROOT)

        backend_health = f"{backend_base}/health"
        if is_ok(backend_health):
            print(f"Reusing backend at {backend_base}")
        elif args.no_start:
            raise RuntimeError(f"Backend is not running at {backend_health}")
        else:
            managed_processes.append(
                start_process(
                    "backend",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        args.host,
                        "--port",
                        str(args.backend_port),
                    ],
                    REPO_ROOT,
                )
            )
            wait_for("backend", backend_health, args.timeout)

        frontend_root = f"{frontend_base}/"
        if is_ok(frontend_root):
            print(f"Reusing frontend at {frontend_base}")
        elif args.no_start:
            raise RuntimeError(f"Frontend is not running at {frontend_root}")
        else:
            npm = shutil.which("npm")
            if npm is None:
                raise RuntimeError("npm was not found in PATH")

            managed_processes.append(
                start_process(
                    "frontend",
                    [
                        npm,
                        "run",
                        "dev",
                        "--",
                        "--host",
                        args.host,
                        "--port",
                        str(args.frontend_port),
                        "--strictPort",
                    ],
                    FRONTEND_DIR,
                )
            )
            wait_for("frontend", frontend_root, args.timeout)

        checks = [
            UrlCheck("backend health", backend_health, '"status":"healthy"'),
            UrlCheck("api root", f"{backend_base}/api/v1/", "Jira Analytics API"),
            UrlCheck("projects reference", f"{backend_base}/api/v1/projects"),
            UrlCheck("employees reference", f"{backend_base}/api/v1/employees"),
            UrlCheck("frontend root", frontend_root, '<div id="root">'),
            UrlCheck("frontend main module", f"{frontend_base}/src/main.tsx", "createRoot"),
        ]

        for check in checks:
            check_url(check)

        print("Local smoke passed.")
        return 0
    except Exception as exc:
        print(f"Local smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_processes(managed_processes)


if __name__ == "__main__":
    raise SystemExit(main())
