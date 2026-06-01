#!/usr/bin/env python3
"""Dynamic preflight check: can the target Odoo image even load the addons?

Spins up the rendered migration container with `--stop-after-init` against
an ephemeral preflight database (not the migration target). Captures
stderr for ImportError / ModuleNotFoundError / Odoo registry errors and
reports them grouped by module.

This is the opt-in deep preflight from decision 11 of the design. It does
not touch the migration database; failure or success here does not change
anything that the main migration will see.

Usage:
    preflight.py --stack-dir PATH --project-dir PATH
                 [--db-service NAME] [--db-user USER]

Expects render_migration_stack.py to have already produced the Dockerfile
and compose file under --stack-dir. Builds the image on demand.
"""

from __future__ import annotations

import argparse
import json
import re
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

PREFLIGHT_DB = "_openupgrade_preflight"

ERROR_PATTERNS = [
    re.compile(r"^(?P<level>ERROR|CRITICAL) (?P<rest>.*)$", re.MULTILINE),
    re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE),
    re.compile(r"ImportError: (?P<msg>.+)$", re.MULTILINE),
    re.compile(r"ModuleNotFoundError: (?P<msg>.+)$", re.MULTILINE),
]

MODULE_FROM_ERROR = re.compile(
    r"odoo\.modules\.module: ([\w\.]+).*",
)


def find_project_compose(project_dir: Path) -> Path:
    for name in COMPOSE_FILENAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No project compose in {project_dir}")


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def find_db_service(project_compose: dict, override: Optional[str]) -> str:
    if override:
        return override
    services = project_compose.get("services") or {}
    for name, service in services.items():
        if (service.get("image") or "").lower().startswith("postgres"):
            return name
    if "db" in services:
        return "db"
    raise ValueError("Could not find a Postgres service in the project compose. Pass --db-service.")


def _strip_compose_var(value: Optional[str], fallback: str) -> str:
    if value is None:
        return fallback
    match = re.match(r"^\$\{[^:}]+:-(?P<default>[^}]+)\}$", value)
    if match:
        return match.group("default")
    if value.startswith("$"):
        return fallback
    return value


def find_db_user(project_compose: dict, service_name: str, override: Optional[str]) -> str:
    if override:
        return override
    service = (project_compose.get("services") or {}).get(service_name, {})
    env = service.get("environment") or {}
    if isinstance(env, list):
        env = dict(s.split("=", 1) for s in env if "=" in s)
    return _strip_compose_var(env.get("POSTGRES_USER"), "odoo")


def project_compose_exec(project_compose: Path, service: str, cmd: list[str], check: bool = True):
    args = ["docker", "compose", "-f", str(project_compose), "exec", "-T", service, *cmd]
    return subprocess.run(args, capture_output=True, check=check)


def ensure_db(project_compose: Path, service: str, user: str, db: str) -> None:
    result = project_compose_exec(
        project_compose, service,
        ["psql", "-U", user, "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{db}'"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip() == b"1":
        return
    project_compose_exec(project_compose, service, ["createdb", "-U", user, "-O", user, db])


def drop_db(project_compose: Path, service: str, user: str, db: str) -> None:
    project_compose_exec(
        project_compose, service,
        ["psql", "-U", user, "-c",
         f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{db}' AND pid <> pg_backend_pid();"],
        check=False,
    )
    project_compose_exec(project_compose, service, ["dropdb", "-U", user, "--if-exists", db], check=False)


def compose_run(stack_compose: Path, command: list[str]) -> subprocess.CompletedProcess:
    args = [
        "docker", "compose", "-f", str(stack_compose),
        "run", "--rm", "--no-deps",
        "openupgrade",
        *command,
    ]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def build_image(stack_compose: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(stack_compose), "build", "openupgrade"],
        check=False,
    )


def analyze_log(log_text: str) -> dict:
    summary = {"errors": 0, "critical": 0, "modules_with_errors": []}
    module_errors: dict[str, list[str]] = {}
    for line in log_text.splitlines():
        if " ERROR " in line:
            summary["errors"] += 1
        if " CRITICAL " in line:
            summary["critical"] += 1
        match = re.search(r"odoo\.modules\.(?:module|loading)[^:]*: ([\w\.]+)", line)
        if match and ("ERROR" in line or "Traceback" in line or "ImportError" in line):
            mod = match.group(1).split(".")[0]
            module_errors.setdefault(mod, []).append(line.strip()[:300])
    summary["modules_with_errors"] = sorted(module_errors.keys())
    return {"summary": summary, "per_module": module_errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stack-dir", type=Path, required=True,
                        help="Directory containing the rendered Dockerfile + compose.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(),
                        help="Project root (where the original docker-compose.yml lives).")
    parser.add_argument("--db-service", default=None,
                        help="Postgres service name in the project compose.")
    parser.add_argument("--db-user", default=None,
                        help="Postgres user (auto-detected from POSTGRES_USER).")
    parser.add_argument("--skip-build", action="store_true",
                        help="Assume the openupgrade image is already built.")
    args = parser.parse_args()

    stack_compose = (args.stack_dir / "docker-compose.openupgrade.yml").resolve()
    if not stack_compose.is_file():
        print(json.dumps({"error": f"stack compose not found: {stack_compose}"}, indent=2))
        return 2

    try:
        project_compose = find_project_compose(args.project_dir.resolve())
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    project_compose_data = _load_yaml(project_compose)
    try:
        db_service = find_db_service(project_compose_data, args.db_service)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    db_user = find_db_user(project_compose_data, db_service, args.db_user)

    if not args.skip_build:
        build = build_image(stack_compose)
        if build.returncode != 0:
            print(json.dumps({"error": "docker compose build failed"}, indent=2))
            return 1

    ensure_db(project_compose, db_service, db_user, PREFLIGHT_DB)
    try:
        result = compose_run(
            stack_compose,
            [
                f"--database={PREFLIGHT_DB}",
                "--stop-after-init",
                "--without-demo=all",
                "--log-level=info",
            ],
        )
    finally:
        drop_db(project_compose, db_service, db_user, PREFLIGHT_DB)

    log_text = (result.stdout or "") + "\n" + (result.stderr or "")
    analysis = analyze_log(log_text)

    print(json.dumps({
        "stack_compose": str(stack_compose),
        "preflight_db": PREFLIGHT_DB,
        "exit_code": result.returncode,
        "log_excerpt": log_text[-4000:],
        **analysis,
    }, indent=2))
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
