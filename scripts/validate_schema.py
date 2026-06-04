#!/usr/bin/env python3
"""
Validate all resources in resources.json against the JSON schema.

Usage:
    python scripts/validate_schema.py

Exit codes:
    0 — All resources valid
    1 — One or more validation errors
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCHEMA_PATH = DATA_DIR / "schema.json"
RESOURCES_PATH = DATA_DIR / "resources.json"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    # Check files exist
    if not SCHEMA_PATH.exists():
        print(f"ERROR: Schema file not found: {SCHEMA_PATH}")
        return 1
    if not RESOURCES_PATH.exists():
        print(f"ERROR: Resources file not found: {RESOURCES_PATH}")
        return 1

    try:
        import jsonschema
    except ImportError:
        print("ERROR: jsonschema package not installed. Run: pip install jsonschema")
        return 1

    schema = load_json(SCHEMA_PATH)
    resources = load_json(RESOURCES_PATH)

    if not isinstance(resources, list):
        print("ERROR: resources.json must be a JSON array")
        return 1

    validator = jsonschema.Draft7Validator(schema)
    total_errors = 0
    valid_count = 0

    for i, resource in enumerate(resources):
        resource_id = resource.get("id", f"<index-{i}>")
        errors = list(validator.iter_errors(resource))

        if errors:
            total_errors += len(errors)
            print(f"\n❌ Resource [{i}] id={resource_id}:")
            for err in errors:
                path = " -> ".join(str(p) for p in err.absolute_path) or "(root)"
                print(f"   {path}: {err.message}")
        else:
            valid_count += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {valid_count}/{len(resources)} resources valid")

    if total_errors > 0:
        print(f"Total errors: {total_errors}")
        print("FAILED ❌")
        return 1

    print("ALL VALID ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
