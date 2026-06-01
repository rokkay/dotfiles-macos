#!/usr/bin/env python3
"""Scaffold migration files for custom Odoo addons.

For each addon directory passed in, this script:
  1. Reads the manifest and bumps the major version to the target.
       18.0.1.2.3 -> 19.0.1.2.3
       1.0.0      -> 19.0.1.0.0 (fallback when the manifest version is not
                                 in the Odoo "N.0.x.y.z" shape)
  2. Creates <addon>/migrations/<new_version>/ with pre-migration.py and
     post-migration.py stubs that include guidance comments.

Idempotent: if the migrations directory already exists, the stubs are not
overwritten; if the manifest version is already at the target, the manifest
is left untouched.

Usage:
    scaffold_custom_migration.py PATH [PATH ...] --target VERSION [--dry-run]

PATH may point to a single addon directory or to a parent directory; the
script iterates through immediate subdirectories that contain a manifest.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Optional


VERSION_RE = re.compile(
    r"""(?P<prefix>["']version["']\s*:\s*["'])(?P<value>[^"']+)(?P<suffix>["'])"""
)

PRE_MIGRATION_TEMPLATE = '''"""Pre-migration script for {addon} -> Odoo {target}.

Runs BEFORE the module is upgraded. Use it for tasks that must happen on
the old schema, such as renaming columns, dropping incompatible
constraints, or stashing data that the upgrade step will need.

Reference: https://oca.github.io/OpenUpgrade/contributing/migration_scripts.html

Available globals:
    env          (None at this stage; the new registry does not exist yet)
    cr           (database cursor)
    version      (the version being upgraded FROM, as a string)
"""


def migrate(cr, version):
    if not version:
        return  # Fresh install, nothing to migrate.

    # TODO: rename columns, drop FKs that block the upgrade, etc.
    # Example:
    #     openupgrade.rename_columns(cr, {{'my_model': [('old_col', 'new_col')]}})
    pass
'''

POST_MIGRATION_TEMPLATE = '''"""Post-migration script for {addon} -> Odoo {target}.

Runs AFTER the module has been upgraded. Use it for data migrations that
need the new ORM, recomputation of stored fields, or cleanup of legacy
records.

Reference: https://oca.github.io/OpenUpgrade/contributing/migration_scripts.html

Available globals:
    env          (a fully-loaded environment on the new schema)
    cr           (database cursor)
    version      (the version being upgraded FROM, as a string)
"""


def migrate(cr, version):
    if not version:
        return

    # TODO: convert data, recompute stored fields, drop legacy columns, etc.
    # Example:
    #     env = api.Environment(cr, SUPERUSER_ID, {{}})
    #     env['my.model'].search([]).write({{'new_field': default}})
    pass
'''


def read_manifest(addon_dir: Path) -> tuple[Optional[Path], Optional[dict], Optional[str]]:
    """Return (path, parsed_dict, raw_text) for the first manifest found."""
    for filename in ("__manifest__.py", "__openerp__.py"):
        path = addon_dir / filename
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            try:
                data = ast.literal_eval(text)
            except (SyntaxError, ValueError) as exc:
                return path, {"_parse_error": str(exc)}, text
            if not isinstance(data, dict):
                return path, {"_parse_error": "manifest is not a dict"}, text
            return path, data, text
    return None, None, None


def bump_version(current: Optional[str], target: str) -> str:
    target_major = target.split(".", 1)[0]
    if not current:
        return f"{target_major}.0.1.0.0"
    parts = current.split(".")
    # Odoo style "N.0.X.Y.Z" -> replace N
    if len(parts) >= 3 and parts[1] == "0":
        return f"{target_major}.0." + ".".join(parts[2:])
    # Otherwise prepend the target prefix.
    return f"{target_major}.0.1.0.0"


def update_manifest_text(text: str, new_version: str) -> tuple[str, Optional[str]]:
    match = VERSION_RE.search(text)
    if not match:
        return text, None
    old_value = match.group("value")
    if old_value == new_version:
        return text, old_value
    new_text = (
        text[: match.start()]
        + match.group("prefix")
        + new_version
        + match.group("suffix")
        + text[match.end() :]
    )
    return new_text, old_value


def iter_addons(path: Path):
    if not path.exists():
        return
    if (path / "__manifest__.py").is_file() or (path / "__openerp__.py").is_file():
        yield path
        return
    for child in sorted(path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "__manifest__.py").is_file() or (child / "__openerp__.py").is_file():
            yield child


def scaffold_one(addon_dir: Path, target: str, dry_run: bool) -> dict:
    name = addon_dir.name
    manifest_path, manifest, raw = read_manifest(addon_dir)
    if manifest is None:
        return {"addon": name, "skipped": True, "reason": "no manifest"}
    if "_parse_error" in manifest:
        return {"addon": name, "skipped": True, "reason": f"parse error: {manifest['_parse_error']}"}

    current_version = manifest.get("version")
    new_version = bump_version(current_version, target)
    new_text, replaced = update_manifest_text(raw, new_version)
    manifest_changed = replaced is not None and replaced != new_version

    migration_dir = addon_dir / "migrations" / new_version
    pre_path = migration_dir / "pre-migration.py"
    post_path = migration_dir / "post-migration.py"

    actions: list[str] = []

    if manifest_changed:
        actions.append(f"manifest: version {replaced!r} -> {new_version!r}")
    elif replaced is None:
        actions.append("manifest: no `version` key found; left untouched")
    else:
        actions.append(f"manifest: version already {new_version!r}, untouched")

    if not migration_dir.exists():
        actions.append(f"create directory {migration_dir.relative_to(addon_dir)}/")
    if not pre_path.exists():
        actions.append(f"create {pre_path.relative_to(addon_dir)}")
    if not post_path.exists():
        actions.append(f"create {post_path.relative_to(addon_dir)}")

    if not dry_run:
        if manifest_changed and manifest_path is not None:
            manifest_path.write_text(new_text, encoding="utf-8")
        migration_dir.mkdir(parents=True, exist_ok=True)
        if not pre_path.exists():
            pre_path.write_text(
                PRE_MIGRATION_TEMPLATE.format(addon=name, target=target),
                encoding="utf-8",
            )
        if not post_path.exists():
            post_path.write_text(
                POST_MIGRATION_TEMPLATE.format(addon=name, target=target),
                encoding="utf-8",
            )

    return {
        "addon": name,
        "path": str(addon_dir),
        "old_version": current_version,
        "new_version": new_version,
        "migration_dir": str(migration_dir),
        "manifest_changed": manifest_changed,
        "actions": actions,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="Addon paths to scaffold.")
    parser.add_argument("--target", required=True, help="Target Odoo version, e.g. 19.0.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without modifying anything on disk.",
    )
    args = parser.parse_args()

    results: list[dict] = []
    for raw_path in args.paths:
        path = raw_path.resolve()
        for addon_dir in iter_addons(path):
            results.append(scaffold_one(addon_dir, args.target, args.dry_run))

    print(
        json.dumps(
            {
                "target_version": args.target,
                "dry_run": args.dry_run,
                "addons": results,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
