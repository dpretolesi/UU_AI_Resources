#!/usr/bin/env python3
"""
Verify no URLs in resources.json or pending/ appear in rejected.json.

Usage:
    python scripts/check_not_rejected.py

Exit codes:
    0 — No rejected URLs found in active resources
    1 — Rejected URLs found
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
REJECTED_PATH = DATA_DIR / "rejected.json"
PENDING_DIR = DATA_DIR / "pending"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    # Load rejected URLs
    if not REJECTED_PATH.exists():
        print("No rejected.json found; nothing to check. ✅")
        return 0

    rejected_data = load_json(REJECTED_PATH)
    rejections = rejected_data.get("rejections", [])

    if not rejections:
        print("Rejection log is empty; nothing to check. ✅")
        return 0

    rejected_hashes: dict[str, str] = {}  # hash -> url
    for entry in rejections:
        url = entry.get("url", "")
        if url:
            rejected_hashes[url_hash(url)] = url

    violations: list[tuple[str, str, str]] = []  # (source, url, rejected_url)

    # Check resources.json
    if RESOURCES_PATH.exists():
        resources = load_json(RESOURCES_PATH)
        if isinstance(resources, list):
            for r in resources:
                url = r.get("url", "")
                h = url_hash(url)
                if h in rejected_hashes:
                    violations.append((
                        f"resources.json#{r.get('id', 'unknown')}",
                        url,
                        rejected_hashes[h],
                    ))

    # Check pending files
    if PENDING_DIR.exists():
        for pending_file in sorted(PENDING_DIR.glob("*.json")):
            try:
                pending = load_json(pending_file)
                url = pending.get("url", "")
                h = url_hash(url)
                if h in rejected_hashes:
                    violations.append((
                        f"pending/{pending_file.name}",
                        url,
                        rejected_hashes[h],
                    ))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARNING: Failed to parse {pending_file.name}: {e}")

    if violations:
        print("❌ Rejected URLs found in active resources:\n")
        for source, url, rejected_url in violations:
            print(f"  Source: {source}")
            print(f"  URL:    {url}")
            print(f"  Rejected URL: {rejected_url}")
            print()
        print(f"VIOLATIONS FOUND: {len(violations)} ❌")
        return 1

    total_checked = 0
    if RESOURCES_PATH.exists():
        total_checked += len(load_json(RESOURCES_PATH))
    if PENDING_DIR.exists():
        total_checked += len(list(PENDING_DIR.glob("*.json")))

    print(f"Checked {total_checked} resources against {len(rejected_hashes)} rejections.")
    print("No rejected URLs in active resources. ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
