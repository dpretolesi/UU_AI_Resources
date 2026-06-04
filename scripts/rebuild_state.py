#!/usr/bin/env python3
import json
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
AGENT_DIR = PROJECT_ROOT / "agent"
STATE_FILE = AGENT_DIR / "state.json"
RESOURCES_FILE = DATA_DIR / "resources.json"
REJECTED_FILE = DATA_DIR / "rejected.json"

def url_hash(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

def main():
    hashes = set()
    
    if RESOURCES_FILE.exists():
        with open(RESOURCES_FILE, "r") as f:
            for r in json.load(f):
                if "url" in r:
                    hashes.add(url_hash(r["url"]))

    if REJECTED_FILE.exists():
        with open(REJECTED_FILE, "r") as f:
            rejected = json.load(f)
            for r in rejected.get("rejections", []):
                if "url" in r:
                    hashes.add(url_hash(r["url"]))

    state = {}
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            state = json.load(f)

    state["known_url_hashes"] = sorted(list(hashes))

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    print(f"Rebuilt state with {len(hashes)} known hashes.")

if __name__ == "__main__":
    main()
