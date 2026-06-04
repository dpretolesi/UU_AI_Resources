#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_FILE = DATA_DIR / "resources.json"
REJECTED_FILE = DATA_DIR / "rejected.json"

def main():
    parser = argparse.ArgumentParser(description="Archive a resource")
    parser.add_argument("--id", required=True, help="Resource ID to remove")
    parser.add_argument("--reason", required=True, help="Reason for removal")
    args = parser.parse_args()

    if not RESOURCES_FILE.exists():
        print("resources.json not found")
        return

    with open(RESOURCES_FILE, "r") as f:
        resources = json.load(f)

    target = None
    for r in resources:
        if r.get("id") == args.id:
            target = r
            r["archived"] = True
            break

    if target:
        with open(RESOURCES_FILE, "w") as f:
            json.dump(resources, f, indent=2)
        print(f"Resource {args.id} archived.")
        
        # also add to rejected.json
        if REJECTED_FILE.exists():
             with open(REJECTED_FILE, "r") as f:
                 rejected = json.load(f)
             
             rejected.setdefault("rejections", []).append({
                 "url": target["url"],
                 "reason": args.reason
             })
             
             with open(REJECTED_FILE, "w") as f:
                 json.dump(rejected, f, indent=2)
             print(f"Added to rejected log.")
             
    else:
        print(f"Resource {args.id} not found.")

if __name__ == "__main__":
    main()
