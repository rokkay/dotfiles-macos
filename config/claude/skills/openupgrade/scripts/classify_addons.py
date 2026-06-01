#!/usr/bin/env python3
"""Classify Odoo addons by how they should be treated during an OpenUpgrade migration.

For each addon found under the given addon paths, returns one of:

    core
        Part of Odoo itself. OpenUpgrade handles it. Currently this script
        does NOT detect core modules (it only sees what the user has on
        disk under their addon paths); core lives inside the OpenUpgrade
        Odoo source and is migrated transparently.

    oca_with_target
        OCA module with the target-version branch available upstream.
        Action: swap the code by cloning the branch.

    oca_without_target
        OCA module without a target-version branch yet. BLOCKING.
        Action: fork & port, or wait.

    third_party_with_target
        Non-OCA third party with target branch available. Action: swap.

    third_party_without_target
        Non-OCA third party without target branch. BLOCKING.

    custom
        Project-owned code with no upstream. Action: scaffold migrations.

    enterprise
        Odoo Enterprise module. BLOCKING. OpenUpgrade does not cover it.

Outputs JSON on stdout.

Usage:
    classify_addons.py PATH [PATH ...] --target VERSION [--project-dir PATH] [--offline] [--ls-remote-timeout SECS]

Network calls: by default the script runs `git ls-remote --heads` against
detected GitHub repos to check whether the target branch exists. The
default per-repo timeout is 90 seconds because git's HTTPS handshake plus
GitHub's protocol negotiation can take well over the typical 10-20 seconds
on slow networks or behind sandboxes. Pass --offline to skip the calls
entirely (target_branch_available will be null).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml


ENTERPRISE_LICENSES = {"OEEL-1", "OPL-1"}

KNOWN_ENTERPRISE_MODULES = {
    "account_accountant", "account_consolidation", "account_reports",
    "account_3way_match", "account_followup", "appointment",
    "approvals", "documents", "documents_spreadsheet", "helpdesk",
    "industry_fsm", "knowledge", "marketing_automation", "marketing_card",
    "planning", "project_enterprise", "quality_control",
    "sale_subscription", "social", "studio", "timesheet_grid",
    "voip", "web_enterprise", "web_studio", "website_helpdesk",
    "website_sale_subscription",
}

GITHUB_URL_RE = re.compile(
    r"github\.com[:/](?P<org>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?(?:/|$)",
    re.IGNORECASE,
)

VALID_OVERRIDE_CATEGORIES = {
    "core", "oca_with_target", "oca_without_target",
    "third_party_with_target", "third_party_without_target",
    "custom", "enterprise",
}


def read_manifest(addon_dir: Path) -> Optional[dict]:
    for filename in ("__manifest__.py", "__openerp__.py"):
        manifest_file = addon_dir / filename
        if manifest_file.is_file():
            text = manifest_file.read_text(encoding="utf-8", errors="replace")
            try:
                value = ast.literal_eval(text)
            except (SyntaxError, ValueError) as exc:
                return {"_parse_error": f"{filename}: {exc}"}
            return value if isinstance(value, dict) else {"_parse_error": "manifest is not a dict"}
    return None


def find_git_remote(start: Path) -> Optional[str]:
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(current), "remote", "get-url", "origin"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
                return result.stdout.strip()
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                return None
        if current.parent == current:
            return None
        current = current.parent


def parse_github_url(url: Optional[str]) -> Optional[tuple[str, str]]:
    if not url:
        return None
    match = GITHUB_URL_RE.search(url)
    if not match:
        return None
    return match.group("org"), match.group("repo")


def remote_has_branch(repo_url: str, branch: str, cache: dict, offline: bool, timeout: float) -> Optional[bool]:
    if offline:
        return None
    cache_key = (repo_url, branch)
    if cache_key in cache:
        return cache[cache_key]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", repo_url, branch],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
        present = result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        present = None
    cache[cache_key] = present
    return present


def load_overrides(project_dir: Path) -> dict:
    override_file = project_dir / ".openupgrade" / "addons.yml"
    if not override_file.is_file():
        return {}
    try:
        with override_file.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse {override_file}: {exc}") from exc
    if not isinstance(data, dict):
        return {}
    addons = data.get("addons") or {}
    return addons if isinstance(addons, dict) else {}


def discover_addons(addons_path: Path):
    if not addons_path.is_dir():
        return
    for child in sorted(addons_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest = read_manifest(child)
        if manifest is None:
            continue
        yield child, manifest


def _detect_repo_signals(manifest: dict, addon_dir: Path) -> tuple[Optional[str], Optional[str], str]:
    """Return (org, repo, source) where source is 'git', 'manifest_website', or 'manifest_author'."""
    git_remote = find_git_remote(addon_dir)
    parsed = parse_github_url(git_remote)
    if parsed:
        return parsed[0], parsed[1], "git"

    website = manifest.get("website") or ""
    parsed = parse_github_url(website)
    if parsed:
        return parsed[0], parsed[1], "manifest_website"

    author = manifest.get("author") or ""
    if "oca" in author.lower() or "odoo community association" in author.lower():
        return "OCA", None, "manifest_author"

    return None, None, "none"


def _category_from_signals(org: Optional[str], has_branch: Optional[bool]) -> str:
    is_oca = bool(org) and org.lower() == "oca"
    if has_branch is True:
        return "oca_with_target" if is_oca else "third_party_with_target"
    if has_branch is False:
        return "oca_without_target" if is_oca else "third_party_without_target"
    # has_branch is None (offline or repo not found / unknown)
    return "oca_without_target" if is_oca else "custom"


def classify_addon(
    addon_dir: Path,
    manifest: dict,
    target: str,
    cache: dict,
    overrides: dict,
    offline: bool,
    ls_remote_timeout: float,
) -> dict:
    name = addon_dir.name
    base = {
        "name": name,
        "path": str(addon_dir),
        "version": manifest.get("version"),
        "license": manifest.get("license"),
        "author": manifest.get("author"),
        "website": manifest.get("website"),
    }

    override = overrides.get(name)
    if isinstance(override, dict):
        category = override.get("category")
        if category not in VALID_OVERRIDE_CATEGORIES:
            base["category"] = "custom"
            base["source"] = "override"
            base["notes"] = f"Invalid override category {category!r}; defaulted to custom."
            base["blocking"] = False
            return base
        base["category"] = category
        base["source"] = "override"
        target_repo = override.get("repo")
        target_branch = override.get("branch") or target
        base["target_repo"] = target_repo
        base["target_branch"] = target_branch
        base["target_branch_available"] = None
        base["notes"] = override.get("notes", "")
        base["blocking"] = category in {
            "oca_without_target",
            "third_party_without_target",
            "enterprise",
        }
        if category in {"oca_with_target", "third_party_with_target"} and target_repo and not offline:
            repo_url = f"https://github.com/{target_repo}"
            base["target_branch_available"] = remote_has_branch(
                repo_url, target_branch, cache, offline, ls_remote_timeout
            )
        return base

    license_field = (manifest.get("license") or "").strip()
    if license_field in ENTERPRISE_LICENSES or name in KNOWN_ENTERPRISE_MODULES:
        base["category"] = "enterprise"
        base["source"] = "license" if license_field in ENTERPRISE_LICENSES else "module_name"
        base["blocking"] = True
        base["notes"] = "Enterprise module. OpenUpgrade does not cover Enterprise."
        return base

    org, repo, signal_source = _detect_repo_signals(manifest, addon_dir)
    if not org:
        base["category"] = "custom"
        base["source"] = signal_source
        base["blocking"] = False
        base["notes"] = "No external repo signal. Treated as custom; scaffolding required."
        return base

    if not repo:
        # Author says OCA but we can't resolve the repo. Cannot check branch.
        base["category"] = "oca_without_target"
        base["source"] = signal_source
        base["target_repo"] = None
        base["target_branch"] = target
        base["target_branch_available"] = None
        base["blocking"] = True
        base["notes"] = (
            "Manifest claims OCA authorship but no repo URL detected. "
            "Add an override in .openupgrade/addons.yml with the correct repo."
        )
        return base

    repo_url = f"https://github.com/{org}/{repo}"
    has_branch = remote_has_branch(repo_url, target, cache, offline, ls_remote_timeout)
    category = _category_from_signals(org, has_branch)

    base["category"] = category
    base["source"] = signal_source
    base["target_repo"] = f"{org}/{repo}"
    base["target_branch"] = target
    base["target_branch_available"] = has_branch
    base["blocking"] = category in {"oca_without_target", "third_party_without_target"}
    if has_branch is None and not offline:
        base["notes"] = "Could not query the upstream repo (network error or repo not found)."
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="Addon directories to scan.")
    parser.add_argument("--target", required=True, help="Target Odoo version, e.g. 19.0.")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root used to find .openupgrade/addons.yml.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip network calls. target_branch_available will be null for OCA/third-party.",
    )
    parser.add_argument(
        "--ls-remote-timeout",
        type=float,
        default=90.0,
        help="Per-repo timeout in seconds for `git ls-remote` (default: 90).",
    )
    args = parser.parse_args()

    try:
        overrides = load_overrides(args.project_dir.resolve())
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    cache: dict = {}
    addons: list[dict] = []
    parse_errors: list[dict] = []

    for raw_path in args.paths:
        path = raw_path.resolve()
        if not path.exists():
            parse_errors.append({"path": str(path), "error": "path does not exist"})
            continue
        for addon_dir, manifest in discover_addons(path):
            if "_parse_error" in manifest:
                parse_errors.append({"path": str(addon_dir), "error": manifest["_parse_error"]})
                continue
            addons.append(
                classify_addon(
                    addon_dir,
                    manifest,
                    args.target,
                    cache,
                    overrides,
                    args.offline,
                    args.ls_remote_timeout,
                )
            )

    by_category: dict[str, list[str]] = {}
    blocking: list[str] = []
    for addon in addons:
        by_category.setdefault(addon["category"], []).append(addon["name"])
        if addon.get("blocking"):
            blocking.append(addon["name"])

    result = {
        "target_version": args.target,
        "addons": addons,
        "summary": {
            "total": len(addons),
            "by_category": {cat: len(names) for cat, names in by_category.items()},
            "blocking": blocking,
        },
        "parse_errors": parse_errors,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
