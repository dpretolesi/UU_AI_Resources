#!/usr/bin/env python3
"""
Generate statistics from resources.json and write to data/stats.json.

Usage:
    python scripts/generate_stats.py

Exit codes:
    0 — Stats generated successfully
    1 — Error reading resources
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
STATS_PATH = DATA_DIR / "stats.json"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main() -> int:
    if not RESOURCES_PATH.exists():
        print(f"ERROR: Resources file not found: {RESOURCES_PATH}")
        return 1

    resources = load_json(RESOURCES_PATH)
    if not isinstance(resources, list):
        print("ERROR: resources.json must be a JSON array")
        return 1

    # Filter out archived resources for active stats
    active_resources = [r for r in resources if not r.get("archived", False)]

    # Compute stats
    type_counter = Counter(r.get("type", "unknown") for r in active_resources)
    tag_counter = Counter(
        tag for r in active_resources for tag in r.get("tags", [])
    )
    access_counter = Counter(
        r.get("access", "unknown") for r in active_resources
    )
    contributors = set()
    for r in active_resources:
        contributors.add(r.get("added_by", "unknown"))

    year_counter = Counter(
        r.get("year") for r in active_resources if r.get("year")
    )

    # Quality score stats
    scores = [r["quality_score"] for r in active_resources if "quality_score" in r]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    min_score = min(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0

    stats = {
        "total_resources": len(resources),
        "active_resources": len(active_resources),
        "archived_resources": len(resources) - len(active_resources),
        "resource_types": len(type_counter),
        "type_breakdown": dict(type_counter.most_common()),
        "unique_tags": len(tag_counter),
        "top_tags": dict(tag_counter.most_common(15)),
        "access_breakdown": dict(access_counter.most_common()),
        "year_breakdown": {
            str(k): v for k, v in sorted(year_counter.items()) if k
        },
        "quality_scores": {
            "average": avg_score,
            "min": min_score,
            "max": max_score,
            "scored_count": len(scores),
        },
        "contributors": len(contributors),
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    save_json(STATS_PATH, stats)

    print("Stats generated successfully:")
    print(f"  Total resources: {stats['total_resources']}")
    print(f"  Active: {stats['active_resources']}")
    print(f"  Archived: {stats['archived_resources']}")
    print(f"  Resource types: {stats['resource_types']}")
    print(f"  Unique tags: {stats['unique_tags']}")
    print(f"  Avg quality score: {avg_score}")
    print(f"  Written to: {STATS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
