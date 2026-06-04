#!/usr/bin/env python3
"""
Check for duplicate URLs across resources.json and data/pending/.

Usage:
    python scripts/check_duplicates.py

Exit codes:
    0 — No duplicates found
    1 — Duplicates detected
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
PENDING_DIR = DATA_DIR / "pending"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    url_map: dict[str, list[str]] = {}  # url_hash -> list of sources
    duplicates_found = False

    # Check resources.json
    if RESOURCES_PATH.exists():
        resources = load_json(RESOURCES_PATH)
        if isinstance(resources, list):
            for r in resources:
                url = r.get("url", "")
                rid = r.get("id", "unknown")
                h = url_hash(url)
                source = f"resources.json#{rid}"
                url_map.setdefault(h, []).append(source)

    # Check pending files
    if PENDING_DIR.exists():
        for pending_file in sorted(PENDING_DIR.glob("*.json")):
            try:
                pending = load_json(pending_file)
                url = pending.get("url", "")
                h = url_hash(url)
                source = f"pending/{pending_file.name}"
                url_map.setdefault(h, []).append(source)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARNING: Failed to parse {pending_file.name}: {e}")

    # Report duplicates
    for h, sources in url_map.items():
        if len(sources) > 1:
            duplicates_found = True
            print(f"❌ Duplicate URL (hash={h}):")
            for source in sources:
                print(f"   - {source}")

    if duplicates_found:
        print(f"\nDUPLICATES FOUND ❌")
        return 1

    total = sum(len(v) for v in url_map.values())
    print(f"No duplicates found across {total} URLs. ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
