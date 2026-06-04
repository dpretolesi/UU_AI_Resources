#!/usr/bin/env python3
"""
Move all validated pending resources into resources.json.

Validates each pending file against the schema, appends valid resources
to resources.json, removes processed pending files, and updates
state.json with new known URL hashes.

Usage:
    python scripts/process_pending.py

Exit codes:
    0 — All pending resources processed successfully
    1 — One or more validation errors (partial processing may occur)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
SCHEMA_PATH = DATA_DIR / "schema.json"
PENDING_DIR = DATA_DIR / "pending"
STATE_PATH = PROJECT_ROOT / "agent" / "state.json"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def validate_resource(resource: dict, schema: dict) -> list[str]:
    """Validate a resource against the schema."""
    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        return [e.message for e in validator.iter_errors(resource)]
    except ImportError:
        print("WARNING: jsonschema not installed; skipping validation")
        return []


def main() -> int:
    # Check for pending files
    if not PENDING_DIR.exists():
        print("No pending directory found. Nothing to process.")
        return 0

    pending_files = sorted(PENDING_DIR.glob("*.json"))
    if not pending_files:
        print("No pending files found. Nothing to process.")
        return 0

    print(f"Found {len(pending_files)} pending file(s) to process.\n")

    # Load schema
    if SCHEMA_PATH.exists():
        schema = load_json(SCHEMA_PATH)
    else:
        print("WARNING: schema.json not found; proceeding without validation")
        schema = None

    # Load existing resources
    if RESOURCES_PATH.exists():
        resources = load_json(RESOURCES_PATH)
    else:
        resources = []

    # Build existing URL hash set for dedup
    existing_hashes: set[str] = {url_hash(r["url"]) for r in resources}

    processed = 0
    skipped = 0
    errors = 0

    for pending_file in pending_files:
        print(f"Processing: {pending_file.name}")

        try:
            resource = load_json(pending_file)
        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON: {e}")
            errors += 1
            continue

        # Validate against schema
        if schema:
            validation_errors = validate_resource(resource, schema)
            if validation_errors:
                print(f"  ❌ Schema validation failed:")
                for err in validation_errors:
                    print(f"     - {err}")
                errors += 1
                continue

        # Check for duplicates
        h = url_hash(resource.get("url", ""))
        if h in existing_hashes:
            print(f"  ⚠️  Duplicate URL; skipping")
            pending_file.unlink()
            skipped += 1
            continue

        # Add to resources
        resources.append(resource)
        existing_hashes.add(h)
        processed += 1
        print(f"  ✅ Added: {resource.get('title', 'Unknown')[:60]}")

        # Remove pending file
        pending_file.unlink()

    # Save updated resources
    save_json(RESOURCES_PATH, resources)
    print(f"\nSaved {len(resources)} total resources to resources.json")

    # Update state.json known hashes
    if STATE_PATH.exists():
        state = load_json(STATE_PATH)
        all_hashes = set(state.get("known_url_hashes", []))
        all_hashes.update(existing_hashes)
        state["known_url_hashes"] = sorted(all_hashes)
        state["total_accepted"] = state.get("total_accepted", 0) + processed
        save_json(STATE_PATH, state)
        print(f"Updated state.json (known_url_hashes: {len(all_hashes)})")

    print(f"\nSummary:")
    print(f"  Processed: {processed}")
    print(f"  Skipped (duplicate): {skipped}")
    print(f"  Errors: {errors}")

    if errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
