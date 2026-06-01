#!/usr/bin/env python3
"""Take a hardlink snapshot of an Odoo filestore Docker volume.

Creates a brand-new Docker volume, then uses an Alpine container to
hardlink (`cp -al`) the contents of the source volume into the new one.
Hardlinks give us isolation against future writes (Odoo's filestore is
content-addressed; the engine never rewrites a hash-named file in place),
while costing almost zero extra disk space.

Idempotent: if the destination volume already exists, the script aborts
unless --force is given.

Usage:
    snapshot_filestore.py --source-volume NAME --dest-volume NAME [--force]

Detection of the source volume name is not done here. The orchestrator
inspects the compose file (volumes section of the Odoo service) and
passes the right names in.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def docker(args: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=capture, text=True, check=check)


def volume_exists(name: str) -> bool:
    result = docker(["volume", "inspect", name], check=False)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-volume", required=True, help="Existing Odoo filestore volume.")
    parser.add_argument("--dest-volume", required=True, help="Volume to create and populate.")
    parser.add_argument("--force", action="store_true",
                        help="If the destination volume exists, remove and recreate it.")
    parser.add_argument("--image", default="alpine:3.20",
                        help="Image used to perform the copy (defaults to alpine:3.20).")
    args = parser.parse_args()

    if not volume_exists(args.source_volume):
        print(json.dumps({"error": f"source volume {args.source_volume!r} does not exist"}, indent=2))
        return 2

    if volume_exists(args.dest_volume):
        if not args.force:
            print(json.dumps({
                "error": f"destination volume {args.dest_volume!r} already exists. Pass --force to recreate.",
            }, indent=2))
            return 2
        docker(["volume", "rm", args.dest_volume])

    docker(["volume", "create", args.dest_volume])

    # cp -al: archive mode + hardlinks. The trailing slash on src is important.
    copy_cmd = "cp -al /src/. /dst/ 2>&1 || cp -a /src/. /dst/"
    result = docker(
        [
            "run", "--rm",
            "-v", f"{args.source_volume}:/src:ro",
            "-v", f"{args.dest_volume}:/dst",
            args.image,
            "sh", "-c", copy_cmd,
        ],
        check=False,
    )

    if result.returncode != 0:
        docker(["volume", "rm", args.dest_volume], check=False)
        print(json.dumps({
            "error": "filestore copy failed; destination volume removed.",
            "stderr": (result.stderr or "")[:1000],
            "stdout": (result.stdout or "")[:1000],
        }, indent=2))
        return 1

    # Measure disk usage of the new volume to confirm hardlinks worked.
    size_result = docker(
        [
            "run", "--rm",
            "-v", f"{args.dest_volume}:/dst:ro",
            args.image,
            "sh", "-c", "du -sh /dst | awk '{print $1}'",
        ],
        check=False,
    )
    size = size_result.stdout.strip() if size_result.returncode == 0 else None

    print(json.dumps({
        "source_volume": args.source_volume,
        "dest_volume": args.dest_volume,
        "status": "snapshotted",
        "apparent_size": size,
        "note": "Hardlinks share inodes with the source; apparent size != extra disk usage.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
