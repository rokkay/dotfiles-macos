#!/usr/bin/env python3
"""Generate the post-migration markdown report.

Combines three sources of information:

  1. The migration log file produced by run_migration.py (errors,
     installation status per module).
  2. Health-check SQL queries comparing the source and migrated
     databases (record counts, lost rows, modules left uninstalled).
  3. The classification JSON produced by classify_addons.py (so the
     report can match log lines back to the addon category).

The report is written to <project-dir>/.openupgrade/v<target-major>/
openupgrade-report-<timestamp>.md by default.

Usage:
    generate_report.py --project-dir PATH --target VERSION
                       --source-db NAME --target-db NAME
                       [--log-path PATH] [--classification PATH]
                       [--db-service NAME] [--db-user USER]
                       [--out PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
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

HEALTH_MODELS = [
    "res_partner",
    "res_users",
    "res_company",
    "product_template",
    "product_product",
    "sale_order",
    "sale_order_line",
    "purchase_order",
    "purchase_order_line",
    "account_move",
    "account_move_line",
    "stock_picking",
    "stock_move",
    "stock_quant",
    "hr_employee",
    "crm_lead",
    "project_project",
    "project_task",
    "mail_message",
    "ir_attachment",
]


def find_compose(project_dir: Path) -> Path:
    for name in COMPOSE_FILENAMES:
        p = project_dir / name
        if p.is_file():
            return p
    raise FileNotFoundError(project_dir)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _strip_var(value: Optional[str], fallback: str) -> str:
    if value is None:
        return fallback
    m = re.match(r"^\$\{[^:}]+:-(?P<default>[^}]+)\}$", value)
    if m:
        return m.group("default")
    if value.startswith("$"):
        return fallback
    return value


def detect_db(compose: dict, override_service: Optional[str], override_user: Optional[str]) -> tuple[str, str]:
    services = compose.get("services") or {}
    name = override_service
    if not name:
        for svc_name, svc in services.items():
            if (svc.get("image") or "").lower().startswith("postgres"):
                name = svc_name
                break
        if not name and "db" in services:
            name = "db"
        if not name:
            raise ValueError("Could not locate the Postgres service. Pass --db-service.")
    svc = services.get(name, {})
    env = svc.get("environment") or {}
    if isinstance(env, list):
        env = dict(s.split("=", 1) for s in env if "=" in s)
    user = override_user or _strip_var(env.get("POSTGRES_USER"), "odoo")
    return name, user


def psql_query(compose_file: Path, service: str, user: str, db: str, sql: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "exec", "-T", service,
         "psql", "-U", user, "-d", db, "-tAc", sql],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def count_table(compose_file: Path, service: str, user: str, db: str, table: str) -> Optional[int]:
    out = psql_query(
        compose_file, service, user, db,
        f"SELECT CASE WHEN to_regclass('public.{table}') IS NULL THEN -1 "
        f"ELSE (SELECT count(*) FROM public.{table}) END;",
    )
    try:
        n = int(out)
        return None if n < 0 else n
    except (TypeError, ValueError):
        return None


def installed_modules(compose_file: Path, service: str, user: str, db: str) -> list[str]:
    out = psql_query(
        compose_file, service, user, db,
        "SELECT name FROM ir_module_module WHERE state='installed' ORDER BY name;",
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def collect_health(compose_file: Path, service: str, user: str, source_db: str, target_db: str) -> dict:
    rows = []
    for table in HEALTH_MODELS:
        src = count_table(compose_file, service, user, source_db, table)
        tgt = count_table(compose_file, service, user, target_db, table)
        if src is None and tgt is None:
            continue
        delta = None
        if src is not None and tgt is not None:
            delta = tgt - src
        rows.append({"table": table, "source": src, "target": tgt, "delta": delta})

    source_modules = installed_modules(compose_file, service, user, source_db)
    target_modules = installed_modules(compose_file, service, user, target_db)
    return {
        "counts": rows,
        "source_modules": source_modules,
        "target_modules": target_modules,
        "missing_after_migration": sorted(set(source_modules) - set(target_modules)),
        "new_after_migration": sorted(set(target_modules) - set(source_modules)),
    }


def parse_log(log_path: Optional[Path]) -> dict:
    if not log_path or not log_path.is_file():
        return {"errors": [], "criticals": [], "modules_with_errors": []}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    errors = [line for line in text.splitlines() if " ERROR " in line]
    criticals = [line for line in text.splitlines() if " CRITICAL " in line]
    module_errors: dict[str, list[str]] = {}
    for line in errors + criticals:
        match = re.search(r"odoo\.modules[^:]*: ([\w\.]+)", line)
        if match:
            mod = match.group(1).split(".")[0]
            module_errors.setdefault(mod, []).append(line.strip()[:300])
    return {
        "errors": errors[:200],
        "criticals": criticals[:50],
        "modules_with_errors": sorted(module_errors.keys()),
        "per_module": module_errors,
    }


def render_markdown(meta: dict, classification: dict, log_info: dict, health: dict) -> str:
    lines = [
        f"# OpenUpgrade migration report",
        "",
        f"- **Generated**: {meta['timestamp']}",
        f"- **Source version → Target version**: `{meta['source_version']} → {meta['target_version']}`",
        f"- **Source DB → Target DB**: `{meta['source_db']} → {meta['target_db']}`",
        f"- **Migration log**: `{meta['log_path']}`",
        "",
        "## Outcome",
        "",
        f"- Errors logged: **{len(log_info['errors'])}**",
        f"- Criticals logged: **{len(log_info['criticals'])}**",
        f"- Modules with errors: **{len(log_info['modules_with_errors'])}**",
        f"- Modules uninstalled after migration: **{len(health['missing_after_migration'])}**",
        f"- Modules newly installed after migration: **{len(health['new_after_migration'])}**",
        "",
    ]

    if classification.get("addons"):
        lines.extend(["## Addon plan vs. result", ""])
        by_cat: dict[str, list[str]] = {}
        for addon in classification["addons"]:
            by_cat.setdefault(addon["category"], []).append(addon["name"])
        for cat in sorted(by_cat):
            names = by_cat[cat]
            lines.append(f"- **{cat}** ({len(names)}): {', '.join(names)}")
        lines.append("")

    lines.extend(["## Health-check counts", "",
                  "| Table | Source | Target | Delta |",
                  "|-------|-------:|-------:|------:|"])
    for row in health["counts"]:
        lines.append(
            f"| `{row['table']}` | "
            f"{row['source'] if row['source'] is not None else '-'} | "
            f"{row['target'] if row['target'] is not None else '-'} | "
            f"{row['delta'] if row['delta'] is not None else '-'} |"
        )
    lines.append("")

    lines.extend(["## Modules NOT installed after migration", ""])
    if health["missing_after_migration"]:
        for mod in health["missing_after_migration"]:
            lines.append(f"- `{mod}`")
    else:
        lines.append("_None._")
    lines.append("")

    lines.extend(["## Modules with errors during migration", ""])
    if log_info["modules_with_errors"]:
        for mod in log_info["modules_with_errors"]:
            lines.append(f"### `{mod}`")
            lines.append("")
            for entry in log_info.get("per_module", {}).get(mod, [])[:10]:
                lines.append(f"- `{entry}`")
            lines.append("")
    else:
        lines.append("_None._")
        lines.append("")

    lines.extend(["## Critical log lines", ""])
    if log_info["criticals"]:
        lines.append("```")
        lines.extend(log_info["criticals"])
        lines.append("```")
    else:
        lines.append("_None._")
    lines.append("")

    lines.extend(["## Next steps", "",
                  "1. Review the modules listed under \"Modules NOT installed after migration\". "
                  "Decide whether to install them, write missing migration scripts, or accept their absence.",
                  "2. Investigate any entry in \"Modules with errors\". Re-run the migration after fixing.",
                  "3. Smoke-test the migrated database by pointing a target-version Odoo container at "
                  f"`{meta['target_db']}` and exercising core flows.",
                  "4. When satisfied, promote the migrated database (rename it over the original, "
                  "or update the project compose to point at it)."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--target", required=True)
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--target-db", required=True)
    parser.add_argument("--source-version", default=None,
                        help="Source version label for the report (e.g. 18.0). "
                             "Defaults to derived target_major-1.")
    parser.add_argument("--log-path", type=Path, default=None)
    parser.add_argument("--classification", type=Path, default=None,
                        help="JSON file produced by classify_addons.py.")
    parser.add_argument("--db-service", default=None)
    parser.add_argument("--db-user", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    try:
        compose_file = find_compose(project_dir)
    except FileNotFoundError as exc:
        print(json.dumps({"error": f"compose not found: {exc}"}, indent=2), file=sys.stderr)
        return 2

    compose = _load_yaml(compose_file)
    try:
        db_service, db_user = detect_db(compose, args.db_service, args.db_user)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    classification = {"addons": []}
    if args.classification and args.classification.is_file():
        classification = json.loads(args.classification.read_text(encoding="utf-8"))

    log_info = parse_log(args.log_path)
    health = collect_health(compose_file, db_service, db_user, args.source_db, args.target_db)

    target_major = args.target.split(".", 1)[0]
    source_version = args.source_version or f"{int(target_major) - 1}.0"

    out_path = args.out
    if not out_path:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = project_dir / ".openupgrade" / f"v{target_major}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"openupgrade-report-{stamp}.md"

    meta = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "source_version": source_version,
        "target_version": args.target,
        "source_db": args.source_db,
        "target_db": args.target_db,
        "log_path": str(args.log_path) if args.log_path else "(no log)",
    }

    markdown = render_markdown(meta, classification, log_info, health)
    out_path.write_text(markdown, encoding="utf-8")

    print(json.dumps({
        "report": str(out_path),
        "counts": health["counts"],
        "missing_after_migration": health["missing_after_migration"],
        "modules_with_errors": log_info["modules_with_errors"],
        "errors_total": len(log_info["errors"]),
        "criticals_total": len(log_info["criticals"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
