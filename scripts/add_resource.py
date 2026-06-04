#!/usr/bin/env python3
"""
Add a new resource to the AI Research Hub.

Usage:
    python scripts/add_resource.py \\
        --url "https://example.com/resource" \\
        --title "My Resource Title" \\
        --type paper \\
        --tags "deep-learning,transformers" \\
        --description "A detailed description of the resource (30-800 chars)." \\
        [--year 2024] \\
        [--institution "MIT"] \\
        [--access free]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
SCHEMA_PATH = DATA_DIR / "schema.json"

VALID_TYPES = [
    "paper", "course", "tutorial", "blog", "video", "tool", "library",
    "framework", "dataset", "book", "podcast", "newsletter", "community",
    "benchmark", "model",
]

VALID_ACCESS = ["free", "freemium", "paid", "open-access", "unknown"]


def load_json(path: Path) -> list | dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: list | dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_id(url: str) -> str:
    """Generate a deterministic ID from the URL using SHA-256."""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"res-{h}"


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def validate_against_schema(resource: dict) -> list[str]:
    """Validate a resource dict against schema.json."""
    try:
        import jsonschema
    except ImportError:
        print("WARNING: jsonschema not installed. Skipping schema validation.")
        return []

    schema = load_json(SCHEMA_PATH)
    validator = jsonschema.Draft7Validator(schema)
    return [e.message for e in validator.iter_errors(resource)]


def check_duplicate(url: str, resources: list[dict]) -> bool:
    """Check if a URL already exists in resources."""
    target_hash = url_hash(url)
    for r in resources:
        if url_hash(r["url"]) == target_hash:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add a new resource to the AI Research Hub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="URL of the resource")
    parser.add_argument("--title", required=True, help="Title (5-200 chars)")
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_TYPES,
        help="Resource type",
    )
    parser.add_argument(
        "--tags",
        required=True,
        help="Comma-separated tags (lowercase-hyphenated, 1-10)",
    )
    parser.add_argument(
        "--description",
        required=True,
        help="Description (30-800 chars)",
    )
    parser.add_argument("--year", type=int, help="Publication year (2017-2030)")
    parser.add_argument("--institution", help="Associated institution")
    parser.add_argument(
        "--access",
        choices=VALID_ACCESS,
        default="unknown",
        help="Access model (default: unknown)",
    )

    args = parser.parse_args()

    # Parse tags
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # Build resource
    resource: dict = {
        "id": generate_id(args.url),
        "title": args.title,
        "url": args.url,
        "type": args.type,
        "tags": tags,
        "description": args.description,
        "added_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "added_by": "human",
        "language": "en",
        "access": args.access,
        "archived": False,
    }

    if args.year:
        resource["year"] = args.year
    if args.institution:
        resource["institution"] = args.institution

    # Validate against schema
    errors = validate_against_schema(resource)
    if errors:
        print("ERROR: Schema validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    # Load existing resources
    if RESOURCES_PATH.exists():
        resources = load_json(RESOURCES_PATH)
    else:
        resources = []

    # Check for duplicates
    if check_duplicate(args.url, resources):
        print(f"ERROR: Resource with URL already exists: {args.url}")
        return 1

    # Append and save
    resources.append(resource)
    save_json(RESOURCES_PATH, resources)
    print(f"SUCCESS: Added resource '{args.title}' (id: {resource['id']})")
    print(f"  URL: {args.url}")
    print(f"  Type: {args.type}")
    print(f"  Tags: {', '.join(tags)}")
    print(f"  Total resources: {len(resources)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
