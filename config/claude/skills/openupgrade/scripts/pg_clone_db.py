#!/usr/bin/env python3
"""Clone a Postgres database inside a Docker Compose stack.

Streams `pg_dump <source>` into `psql` running against a freshly created
target database, all inside the existing db container of the user's
compose stack. No data leaves the container; no intermediate file on the
host.

Idempotent: if the target database already exists, the script aborts
unless --drop-existing is given.

Usage:
    pg_clone_db.py --project-dir PATH --source DB --target DB
                  [--db-service NAME] [--db-user USER] [--drop-existing]
                  [--compose-file FILE]

Detection: if --db-service is not given, the script looks for a service in
the compose file using a Postgres image (`postgres:*`).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml


COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def find_compose_file(project_dir: Path, override: Optional[Path]) -> Path:
    if override:
        if not override.is_file():
            raise FileNotFoundError(override)
        return override.resolve()
    for name in COMPOSE_FILENAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No compose file in {project_dir}")


def load_compose(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def find_db_service(compose: dict) -> Optional[tuple[str, dict]]:
    services = compose.get("services") or {}
    for name, service in services.items():
        image = (service.get("image") or "").lower()
        if image.startswith("postgres") or image.startswith("docker.io/library/postgres"):
            return name, service
    if "db" in services:
        return "db", services["db"]
    return None


def detect_db_user(service: dict, override: Optional[str]) -> str:
    if override:
        return override
    env = service.get("environment") or {}
    if isinstance(env, list):
        env = dict(s.split("=", 1) for s in env if "=" in s)
    for key in ("POSTGRES_USER", "PGUSER"):
        value = env.get(key)
        if isinstance(value, str) and not value.startswith("$"):
            return value
    return "odoo"


def compose_exec(
    compose_file: Path,
    service: str,
    cmd: list[str],
    *,
    input_data: Optional[bytes] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    args = [
        "docker", "compose", "-f", str(compose_file),
        "exec", "-T", service, *cmd,
    ]
    return subprocess.run(
        args,
        input=input_data,
        capture_output=capture,
        check=check,
    )


def db_exists(compose_file: Path, service: str, user: str, db_name: str) -> bool:
    result = compose_exec(
        compose_file,
        service,
        ["psql", "-U", user, "-tAc",
         f"SELECT 1 FROM pg_database WHERE datname='{db_name}'"],
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == b"1"


def terminate_connections(compose_file: Path, service: str, user: str, db_name: str) -> None:
    sql = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname='{db_name}' AND pid <> pg_backend_pid();"
    )
    compose_exec(compose_file, service, ["psql", "-U", user, "-c", sql], check=False)


def drop_db(compose_file: Path, service: str, user: str, db_name: str) -> None:
    terminate_connections(compose_file, service, user, db_name)
    compose_exec(compose_file, service, ["dropdb", "-U", user, "--if-exists", db_name])


def create_db(compose_file: Path, service: str, user: str, db_name: str, template: str) -> None:
    # Cannot use --template directly with createdb because that does a fast
    # template copy which requires no active sessions. We instead create an
    # empty DB and stream a dump from the source. This is slower but safer.
    compose_exec(compose_file, service, ["createdb", "-U", user, "-O", user, db_name])


def clone_via_pipeline(compose_file: Path, service: str, user: str, source: str, target: str) -> int:
    """Run `pg_dump <source> | psql <target>` inside the db container."""
    cmd = [
        "docker", "compose", "-f", str(compose_file),
        "exec", "-T", service,
        "bash", "-c",
        f"pg_dump -U {user} {source} | psql -U {user} -v ON_ERROR_STOP=1 -q {target}",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr or b"")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--compose-file", type=Path, default=None)
    parser.add_argument("--source", required=True, help="Source database name.")
    parser.add_argument("--target", required=True, help="Target database name to create.")
    parser.add_argument("--db-service", default=None,
                        help="Compose service name of the Postgres container.")
    parser.add_argument("--db-user", default=None,
                        help="Postgres user (auto-detected from POSTGRES_USER if absent).")
    parser.add_argument("--drop-existing", action="store_true",
                        help="If the target DB exists, drop it first.")
    args = parser.parse_args()

    try:
        compose_file = find_compose_file(args.project_dir.resolve(), args.compose_file)
    except FileNotFoundError as exc:
        print(json.dumps({"error": f"compose file not found: {exc}"}, indent=2))
        return 2

    compose = load_compose(compose_file)

    if args.db_service:
        service_name = args.db_service
        service = (compose.get("services") or {}).get(service_name, {})
    else:
        detected = find_db_service(compose)
        if not detected:
            print(json.dumps({"error": "No Postgres service detected. Pass --db-service."}, indent=2))
            return 2
        service_name, service = detected

    user = detect_db_user(service, args.db_user)

    if not db_exists(compose_file, service_name, user, args.source):
        print(json.dumps({"error": f"source database {args.source!r} does not exist"}, indent=2))
        return 2

    if db_exists(compose_file, service_name, user, args.target):
        if not args.drop_existing:
            print(json.dumps({
                "error": f"target database {args.target!r} already exists. Pass --drop-existing to replace it.",
            }, indent=2))
            return 2
        drop_db(compose_file, service_name, user, args.target)

    create_db(compose_file, service_name, user, args.target, args.source)
    rc = clone_via_pipeline(compose_file, service_name, user, args.source, args.target)
    if rc != 0:
        drop_db(compose_file, service_name, user, args.target)
        print(json.dumps({
            "error": "pg_dump | psql pipeline failed; target database dropped.",
            "compose_file": str(compose_file),
            "service": service_name,
        }, indent=2))
        return 1

    print(json.dumps({
        "compose_file": str(compose_file),
        "db_service": service_name,
        "db_user": user,
        "source": args.source,
        "target": args.target,
        "status": "cloned",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
