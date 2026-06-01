#!/usr/bin/env python3
"""Detect the source Odoo version and addon mount paths from a Docker Compose project.

Reads the project's compose file, identifies the Odoo service, extracts the
image tag (or build arg), parses the version like "18.0", and suggests the
next major as the migration target.

Outputs JSON on stdout. Exit code 0 on success, 2 on detection failure
(missing compose file, no Odoo service found).

Usage:
    detect_versions.py [--project-dir PATH] [--target VERSION] [--source-version VERSION]

The script never makes network calls.
"""

from __future__ import annotations

import argparse
import json
import re
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

ODOO_VERSION_RE = re.compile(r"(?P<version>\d{1,2}\.0)\b")
COMPOSE_VAR_RE = re.compile(r"^\$\{[^:}]+:-(?P<default>[^}]+)\}$")


def find_compose_file(project_dir: Path) -> Path:
    for name in COMPOSE_FILENAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No compose file found in {project_dir} (looked for {', '.join(COMPOSE_FILENAMES)})"
    )


def load_compose(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}


def looks_like_odoo_service(name: str, service: dict) -> bool:
    image = (service.get("image") or "").lower()
    if "odoo" in image:
        return True
    build = service.get("build")
    if isinstance(build, dict):
        args = _normalize_build_args(build.get("args"))
        if any("odoo" in key.lower() for key in args):
            return True
        if any("odoo" in str(value).lower() for value in args.values()):
            return True
        dockerfile = build.get("dockerfile") or ""
        if "odoo" in dockerfile.lower():
            return True
    return name.lower() in {"odoo", "web"}


def _normalize_build_args(args) -> dict:
    if not args:
        return {}
    if isinstance(args, dict):
        return {str(k): str(v) for k, v in args.items()}
    if isinstance(args, list):
        out = {}
        for entry in args:
            if isinstance(entry, str) and "=" in entry:
                key, value = entry.split("=", 1)
                out[key] = value
        return out
    return {}


def find_odoo_service(compose: dict) -> tuple[str, dict]:
    services = compose.get("services") or {}
    matches = [(name, svc) for name, svc in services.items() if looks_like_odoo_service(name, svc)]
    if not matches:
        raise ValueError("No service in the compose file looks like Odoo.")
    if len(matches) == 1:
        return matches[0]
    # Prefer explicit image:odoo
    for name, svc in matches:
        if "odoo" in (svc.get("image") or "").lower():
            return name, svc
    return matches[0]


def extract_image_tag(service: dict) -> Optional[str]:
    image = service.get("image")
    if isinstance(image, str) and ":" in image:
        return image.split(":", 1)[1]
    build = service.get("build")
    if isinstance(build, dict):
        args = _normalize_build_args(build.get("args"))
        for key in ("ODOO_IMAGE_TAG", "ODOO_VERSION", "ODOO_TAG", "VERSION"):
            if key in args:
                return args[key]
    return None


def parse_version(tag: Optional[str]) -> Optional[str]:
    if not tag:
        return None
    # ${VAR:-default} → default
    match_var = COMPOSE_VAR_RE.match(tag)
    if match_var:
        tag = match_var.group("default")
    match = ODOO_VERSION_RE.search(tag)
    return match.group("version") if match else None


def suggest_target(source: str) -> str:
    major = int(source.split(".", 1)[0])
    return f"{major + 1}.0"


def extract_addons_paths(service: dict, compose_dir: Path) -> list[str]:
    """Best-effort extraction of addons mount paths from the Odoo service volumes.

    Heuristic: any volume whose target path contains 'addon' or starts with '/mnt/'
    is considered an addons mount. Returns absolute host paths.
    """
    volumes = service.get("volumes") or []
    addon_hosts: list[str] = []
    for entry in volumes:
        host, target = _parse_volume(entry)
        if host is None or target is None:
            continue
        if not _looks_like_addons_mount(target):
            continue
        resolved = _resolve_host_path(host, compose_dir)
        if resolved is not None:
            addon_hosts.append(str(resolved))
    return addon_hosts


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
    if "addon" in lowered:
        return True
    if lowered.startswith("/mnt/"):
        return True
    return False


def _resolve_host_path(host: str, compose_dir: Path) -> Optional[Path]:
    # Named volumes (no slash, no dot prefix) cannot be inspected from the host.
    if not host.startswith((".", "/", "~")):
        return None
    path = Path(host).expanduser()
    if not path.is_absolute():
        path = (compose_dir / path).resolve()
    else:
        path = path.resolve()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root (defaults to current working directory).",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Force a target version (e.g. 19.0). Defaults to source major + 1.",
    )
    parser.add_argument(
        "--source-version",
        type=str,
        default=None,
        help="Override the detected source version (e.g. 18.0).",
    )
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    warnings: list[str] = []

    try:
        compose_path = find_compose_file(project_dir)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    compose = load_compose(compose_path)

    try:
        service_name, service = find_odoo_service(compose)
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "compose_file": str(compose_path)}, indent=2))
        return 2

    image_tag = extract_image_tag(service)
    source = args.source_version or parse_version(image_tag)
    if not source:
        warnings.append(
            f"Could not parse an Odoo version from image tag {image_tag!r}. "
            "Pass --source-version explicitly."
        )

    target = args.target or (suggest_target(source) if source else None)
    if target and source and target == source:
        warnings.append("Target version equals source version; nothing to migrate.")

    addons_paths = extract_addons_paths(service, compose_path.parent)
    missing_paths = [p for p in addons_paths if not Path(p).exists()]
    if missing_paths:
        warnings.append(
            "Addons mount paths declared in compose but missing on disk: "
            + ", ".join(missing_paths)
        )

    result = {
        "compose_file": str(compose_path),
        "service_name": service_name,
        "image_tag": image_tag,
        "source_version": source,
        "target_version": target,
        "addons_paths": addons_paths,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
