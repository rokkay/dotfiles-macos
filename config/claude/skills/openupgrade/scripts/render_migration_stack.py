#!/usr/bin/env python3
"""Render the migration Dockerfile and docker-compose used by the OpenUpgrade pass.

Inspects the project's compose file to learn the db service, credentials,
and existing addon mounts, then produces:

  <out-dir>/Dockerfile.openupgrade
  <out-dir>/docker-compose.openupgrade.yml

These artefacts are isolated from the project's main compose: they only
read addons (mounted :ro) and write to the migration filestore volume
plus the migration database. The original `web` service stays untouched.

Usage:
    render_migration_stack.py --project-dir PATH --target VERSION
                              --target-db NAME --filestore-volume NAME
                              [--out-dir PATH] [--python-version 3.12]
                              [--addons-paths PATH ...]
                              [--db-service NAME]

By default --addons-paths is taken from the project compose (mount targets
containing 'addon' or under /mnt/), each remapped to its target-version
sibling under the same renaming heuristic as clone_oca_branches.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SKILL_ROOT / "templates"

COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def find_compose_file(project_dir: Path, override: Optional[Path]) -> Path:
    if override:
        return override.resolve()
    for name in COMPOSE_FILENAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No compose file in {project_dir}")


def load_compose(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _normalize_env(env) -> dict:
    if not env:
        return {}
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    if isinstance(env, list):
        out = {}
        for entry in env:
            if isinstance(entry, str) and "=" in entry:
                key, value = entry.split("=", 1)
                out[key] = value
        return out
    return {}


def _strip_compose_var(value: Optional[str], fallback: str = "") -> str:
    if value is None:
        return fallback
    match = re.match(r"^\$\{[^:}]+:-(?P<default>[^}]+)\}$", value)
    if match:
        return match.group("default")
    if value.startswith("$"):
        return fallback
    return value


def find_odoo_service(compose: dict) -> tuple[str, dict]:
    services = compose.get("services") or {}
    for name, service in services.items():
        if "odoo" in (service.get("image") or "").lower():
            return name, service
        build = service.get("build") or {}
        if isinstance(build, dict):
            args = build.get("args") or {}
            if isinstance(args, dict) and any("ODOO" in str(k).upper() for k in args):
                return name, service
        if name.lower() in {"web", "odoo"}:
            return name, service
    raise ValueError("Could not locate the Odoo service in the compose file.")


def find_db_service(compose: dict) -> tuple[str, dict]:
    services = compose.get("services") or {}
    for name, service in services.items():
        if (service.get("image") or "").lower().startswith("postgres"):
            return name, service
    if "db" in services:
        return "db", services["db"]
    raise ValueError("Could not locate the Postgres service in the compose file.")


def extract_addons_mounts(odoo_service: dict, compose_dir: Path, target_major: str) -> list[dict]:
    volumes = odoo_service.get("volumes") or []
    mounts = []
    for entry in volumes:
        host, target = _parse_volume(entry)
        if not host or not target:
            continue
        if not _looks_like_addons_mount(target):
            continue
        host_path = _resolve_host_path(host, compose_dir)
        if host_path is None:
            continue
        new_host = _remap_host_to_target(host_path, target_major)
        mounts.append({"host": str(new_host), "container": target})
    return mounts


def _parse_volume(entry) -> tuple[Optional[str], Optional[str]]:
    if isinstance(entry, str):
        parts = entry.split(":")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None, None
    if isinstance(entry, dict):
        return entry.get("source"), entry.get("target")
    return None, None


def _looks_like_addons_mount(target: str) -> bool:
    lowered = target.lower()
    return "addon" in lowered or lowered.startswith("/mnt/")


def _resolve_host_path(host: str, compose_dir: Path) -> Optional[Path]:
    if not host.startswith((".", "/", "~")):
        return None
    path = Path(host).expanduser()
    if not path.is_absolute():
        path = (compose_dir / path).resolve()
    else:
        path = path.resolve()
    return path


def _remap_host_to_target(host_path: Path, target_major: str) -> Path:
    name = host_path.name
    new_name = re.sub(r"-\d+$", f"-{target_major}", name)
    if new_name == name:
        new_name = f"{name}-{target_major}"
    return host_path.parent / new_name


def detect_db_credentials(db_service: dict) -> tuple[str, str]:
    env = _normalize_env(db_service.get("environment"))
    user = _strip_compose_var(env.get("POSTGRES_USER"), "odoo")
    password = _strip_compose_var(env.get("POSTGRES_PASSWORD"), "odoo")
    return user, password


def detect_project_name(compose: dict, project_dir: Path) -> str:
    name = compose.get("name")
    if isinstance(name, str) and name:
        return _strip_compose_var(name, project_dir.name)
    return project_dir.name


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return slug.strip("._-") or "project"


def render(project_dir: Path, args) -> dict:
    compose_file = find_compose_file(project_dir, args.compose_file)
    compose = load_compose(compose_file)
    target = args.target
    target_major = target.split(".", 1)[0]

    odoo_service_name, odoo_service = find_odoo_service(compose)

    if args.db_service:
        db_service_name = args.db_service
        db_service = (compose.get("services") or {}).get(db_service_name) or {}
    else:
        db_service_name, db_service = find_db_service(compose)

    db_user, db_password = detect_db_credentials(db_service)
    project_name = slugify(detect_project_name(compose, project_dir))

    if args.addons_paths:
        addons_mounts = []
        for spec in args.addons_paths:
            if "=" in spec:
                host, container = spec.split("=", 1)
            else:
                host, container = spec, f"/mnt/{Path(spec).name}"
            addons_mounts.append({"host": host, "container": container})
    else:
        addons_mounts = extract_addons_mounts(odoo_service, compose_file.parent, target_major)

    addons_path_arg = ",".join(m["container"] for m in addons_mounts) or "/mnt/extra-addons"

    out_dir = (args.out_dir or (project_dir / ".openupgrade" / f"v{target_major}")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dockerfile_out = out_dir / "Dockerfile.openupgrade"
    compose_out = out_dir / "docker-compose.openupgrade.yml"

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    dockerfile = env.get_template("Dockerfile.openupgrade.j2").render(
        python_version=args.python_version,
        target_version=target,
    )
    dockerfile_out.write_text(dockerfile, encoding="utf-8")

    project_network = args.network_name or f"{project_name}_default"
    db_host = args.db_host or db_service_name

    compose_yaml = env.get_template("docker-compose.openupgrade.yml.j2").render(
        project_slug=project_name,
        target_version=target,
        target_major=target_major,
        target_db=args.target_db,
        build_context=str(out_dir),
        dockerfile_path=dockerfile_out.name,
        project_network=project_network,
        db_host=db_host,
        db_user=db_user,
        db_password=db_password,
        filestore_volume=args.filestore_volume,
        addons_mounts=addons_mounts,
        addons_path=addons_path_arg,
        external_volumes=[args.filestore_volume],
    )
    compose_out.write_text(compose_yaml, encoding="utf-8")

    return {
        "project": project_name,
        "out_dir": str(out_dir),
        "dockerfile": str(dockerfile_out),
        "compose_file": str(compose_out),
        "target_db": args.target_db,
        "filestore_volume": args.filestore_volume,
        "db_service": db_service_name,
        "db_user": db_user,
        "db_host": db_host,
        "addons_mounts": addons_mounts,
        "project_network": project_network,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--compose-file", type=Path, default=None)
    parser.add_argument("--target", required=True, help="Target Odoo version, e.g. 19.0.")
    parser.add_argument("--target-db", required=True, help="Migration database name.")
    parser.add_argument("--filestore-volume", required=True,
                        help="Migration filestore volume (already created by snapshot_filestore.py).")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Where to write the generated files. Defaults to <project>/.openupgrade/v<target_major>/.")
    parser.add_argument("--python-version", default="3.12",
                        help="Python base image tag (default: 3.12).")
    parser.add_argument("--addons-paths", nargs="*", default=None,
                        help="Override addon mounts. Each entry can be HOST or HOST=CONTAINER.")
    parser.add_argument("--db-service", default=None,
                        help="Compose service name of Postgres (auto-detected by default).")
    parser.add_argument("--db-host", default=None,
                        help="Hostname the migration container will reach Postgres on. "
                             "Defaults to the db service name (resolved on the project network).")
    parser.add_argument("--network-name", default=None,
                        help="Existing Docker network to join. Defaults to <project>_default, "
                             "which is the network Compose auto-creates for the project.")
    args = parser.parse_args()

    try:
        info = render(args.project_dir.resolve(), args)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
