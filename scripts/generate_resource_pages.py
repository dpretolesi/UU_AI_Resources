#!/usr/bin/env python3
import json
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SITE_DIR = PROJECT_ROOT / "site"
RESOURCES_DIR = SITE_DIR / "resources"

def main():
    resources_path = DATA_DIR / "resources.json"
    if not resources_path.exists():
        print(f"File not found: {resources_path}")
        return

    with open(resources_path, "r", encoding="utf-8") as f:
        resources = json.load(f)

    if RESOURCES_DIR.exists():
        shutil.rmtree(RESOURCES_DIR)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    for resource in resources:
        res_id = resource.get("id")
        if not res_id:
            continue

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{resource.get('title', '')}</title>
</head>
<body>
    <article data-pagefind-body data-pagefind-meta="title:{resource.get('title', '')}, type:{resource.get('type', '')}">
        <h1>{resource.get('title', '')}</h1>
        <p>{resource.get('description', '')}</p>
        <span data-pagefind-filter="type">{resource.get('type', '')}</span>
        <span data-pagefind-filter="access">{resource.get('access', 'unknown')}</span>
"""
        for tag in resource.get("tags", []):
            html_content += f'        <span data-pagefind-filter="tags">{tag}</span>\n'

        html_content += """    </article>
</body>
</html>"""

        with open(RESOURCES_DIR / f"{res_id}.html", "w", encoding="utf-8") as f:
            f.write(html_content)

    print(f"Generated {len(resources)} static pages in site/resources/")

if __name__ == "__main__":
    main()
