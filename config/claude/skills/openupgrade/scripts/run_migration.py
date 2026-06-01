#!/usr/bin/env python3
"""Run the actual OpenUpgrade migration: `odoo -u all --stop-after-init`.

Streams the container logs to stdout as they happen (so the user can see
the migration progress in real time) and tees them into a file inside the
filestore volume. Exits with the container's return code.

Usage:
    run_migration.py --stack-dir PATH [--skip-build] [--log-path PATH]

Expects render_migration_stack.py to have already produced the stack files
and pg_clone_db.py / snapshot_filestore.py to have prepared the target DB
and filestore volume. The OpenUpgrade container itself is configured by
the rendered compose to run `--update=all --stop-after-init`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def docker_compose(stack_compose: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(stack_compose), *args],
        check=check,
    )


def build_image(stack_compose: Path) -> int:
    return subprocess.run(
        ["docker", "compose", "-f", str(stack_compose), "build", "openupgrade"],
    ).returncode


def stream_migration(stack_compose: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()

    # `up --abort-on-container-exit --exit-code-from openupgrade` waits for
    # the container, streams its logs to our stdout, and propagates the exit
    # code. `--remove-orphans` cleans up if a previous run left containers.
    cmd = [
        "docker", "compose", "-f", str(stack_compose),
        "up",
        "--abort-on-container-exit",
        "--exit-code-from", "openupgrade",
        "--remove-orphans",
    ]

    with log_path.open("wb") as log_handle:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        try:
            assert proc.stdout is not None
            for chunk in iter(lambda: proc.stdout.read(4096), b""):
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                log_handle.write(chunk)
        except KeyboardInterrupt:
            proc.terminate()
            raise
        proc.wait()

    elapsed = time.time() - started

    # Capture the in-container log (the one Odoo wrote to /var/lib/odoo/openupgrade.log)
    # via a side container that mounts the same filestore volume.
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stack-dir", type=Path, required=True,
                        help="Directory containing the rendered Dockerfile + compose.")
    parser.add_argument("--skip-build", action="store_true",
                        help="Assume the openupgrade image is already built.")
    parser.add_argument("--log-path", type=Path, default=None,
                        help="Where to tee container logs. Defaults to <stack-dir>/migration.log.")
    args = parser.parse_args()

    stack_compose = (args.stack_dir / "docker-compose.openupgrade.yml").resolve()
    if not stack_compose.is_file():
        print(json.dumps({"error": f"stack compose not found: {stack_compose}"}, indent=2),
              file=sys.stderr)
        return 2

    log_path = args.log_path or (args.stack_dir / "migration.log")

    if not args.skip_build:
        rc = build_image(stack_compose)
        if rc != 0:
            print(json.dumps({"error": "docker compose build failed"}, indent=2),
                  file=sys.stderr)
            return 1

    started = time.time()
    exit_code = stream_migration(stack_compose, log_path)
    elapsed = round(time.time() - started, 1)

    # Clean up: stop and remove containers (volumes survive).
    docker_compose(stack_compose, ["down", "--remove-orphans"], check=False)

    summary = {
        "stack_compose": str(stack_compose),
        "log_path": str(log_path),
        "exit_code": exit_code,
        "elapsed_seconds": elapsed,
        "status": "succeeded" if exit_code == 0 else "failed",
    }
    print("\n" + json.dumps(summary, indent=2), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
