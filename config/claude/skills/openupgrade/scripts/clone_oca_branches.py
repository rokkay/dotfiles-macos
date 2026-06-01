#!/usr/bin/env python3
"""Clone the target-version branches of OCA / third-party repos referenced by addons.

Takes the JSON output of classify_addons.py on stdin (or via --input) and
clones the `target_branch` of each addon whose category is
`oca_with_target` or `third_party_with_target` into a destination directory.

The destination defaults to a sibling of each repo's original path:
  /workspaces/proj/third-party-addons-18/web_responsive
  -> /workspaces/proj/third-party-addons-19/

Idempotent: if the destination already exists and points at the right
remote/branch, it is left alone (or fast-forwarded with --update).

Usage:
    classify_addons.py ... | clone_oca_branches.py [--update] [--dest-pattern PATTERN]

`--dest-pattern` is a Python format string. Available placeholders:
    {project_dir}      Absolute path of --project-dir.
    {addon_dir}        Absolute path of the addon source directory.
    {addon_parent}     Absolute path of the addon parent directory.
    {addon_parent_name} Basename of the addon parent.
    {repo}             "<org>/<repo>" of the upstream.
    {repo_name}        Just the repo basename.
    {target}           Target version (e.g. "19.0").
    {target_major}     Target major (e.g. "19").

Default pattern:
    {addon_parent_renamed_to_target}
which expands the addon's parent directory name, replacing any trailing
"-<digits>" with "-{target_major}". Example:
    third-party-addons-18 -> third-party-addons-19
The script clones each unique upstream once per dest directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


def derive_renamed_parent(addon_parent: Path, target_major: str) -> Path:
    name = addon_parent.name
    new_name = re.sub(r"-\d+$", f"-{target_major}", name)
    if new_name == name:
        new_name = f"{name}-{target_major}"
    return addon_parent.parent / new_name


def resolve_dest(addon: dict, project_dir: Path, target: str, pattern: Optional[str]) -> Path:
    target_major = target.split(".", 1)[0]
    addon_dir = Path(addon["path"]).resolve()
    addon_parent = addon_dir.parent
    repo = addon.get("target_repo") or ""
    repo_name = repo.split("/", 1)[-1] if repo else ""

    if not pattern:
        return derive_renamed_parent(addon_parent, target_major)

    return Path(
        pattern.format(
            project_dir=str(project_dir),
            addon_dir=str(addon_dir),
            addon_parent=str(addon_parent),
            addon_parent_name=addon_parent.name,
            repo=repo,
            repo_name=repo_name,
            target=target,
            target_major=target_major,
        )
    ).resolve()


def run_git(args: list[str], cwd: Optional[Path] = None, timeout: float = 120.0) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout,
    )


def clone_repo(repo: str, branch: str, dest: Path, update: bool) -> dict:
    repo_url = f"https://github.com/{repo}"
    result: dict = {"repo": repo, "branch": branch, "dest": str(dest)}

    if dest.exists():
        existing_remote = run_git(["-C", str(dest), "remote", "get-url", "origin"])
        existing_branch = run_git(["-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"])
        if existing_remote.returncode == 0 and existing_branch.returncode == 0:
            same_remote = existing_remote.stdout.strip().rstrip("/").endswith(f"{repo}.git") \
                or existing_remote.stdout.strip().rstrip("/").endswith(repo)
            same_branch = existing_branch.stdout.strip() == branch
            if same_remote and same_branch:
                result["status"] = "exists"
                if update:
                    pull = run_git(["-C", str(dest), "pull", "--ff-only"], timeout=180)
                    result["status"] = "updated" if pull.returncode == 0 else "exists_pull_failed"
                    if pull.returncode != 0:
                        result["error"] = pull.stderr.strip()[:400]
                return result
        result["status"] = "skipped_dest_in_use"
        result["error"] = f"{dest} exists and does not match {repo}@{branch}"
        return result

    dest.parent.mkdir(parents=True, exist_ok=True)
    clone = run_git(
        ["clone", "--branch", branch, "--single-branch", "--depth", "1", repo_url, str(dest)],
        timeout=300,
    )
    if clone.returncode != 0:
        result["status"] = "clone_failed"
        result["error"] = clone.stderr.strip()[:400]
        return result

    result["status"] = "cloned"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to a classify_addons.py JSON output. Defaults to stdin.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root used to resolve relative paths in --dest-pattern.",
    )
    parser.add_argument(
        "--dest-pattern",
        default=None,
        help="Format string for destination paths (see module docstring).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="If a destination already exists at the right remote/branch, fast-forward it.",
    )
    parser.add_argument(
        "--only-category",
        action="append",
        default=None,
        help="Restrict to one category (repeatable). Defaults to oca_with_target + third_party_with_target.",
    )
    args = parser.parse_args()

    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        data = json.load(sys.stdin)

    target = data["target_version"]
    categories = set(args.only_category or {"oca_with_target", "third_party_with_target"})

    grouped: dict[tuple[str, str, str], dict] = {}
    for addon in data.get("addons", []):
        if addon.get("category") not in categories:
            continue
        repo = addon.get("target_repo")
        branch = addon.get("target_branch") or target
        if not repo:
            continue
        dest = resolve_dest(addon, args.project_dir.resolve(), target, args.dest_pattern)
        key = (repo, branch, str(dest))
        if key not in grouped:
            grouped[key] = {"repo": repo, "branch": branch, "dest": dest, "addons": []}
        grouped[key]["addons"].append(addon["name"])

    operations = []
    for entry in grouped.values():
        result = clone_repo(entry["repo"], entry["branch"], entry["dest"], args.update)
        result["addons"] = entry["addons"]
        operations.append(result)

    print(
        json.dumps(
            {
                "target_version": target,
                "operations": operations,
                "summary": {
                    "total": len(operations),
                    "by_status": _count_by_status(operations),
                },
            },
            indent=2,
        )
    )
    return 0 if all(op["status"] in {"cloned", "exists", "updated"} for op in operations) else 1


def _count_by_status(operations):
    counts: dict[str, int] = {}
    for op in operations:
        counts[op["status"]] = counts.get(op["status"], 0) + 1
    return counts


if __name__ == "__main__":
    sys.exit(main())
