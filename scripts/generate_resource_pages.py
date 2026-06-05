#!/usr/bin/env python3
import json
import html
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

    generated = 0
    for resource in resources:
        # Skip archived resources
        if resource.get("archived", False):
            continue

        res_id = resource.get("id")
        if not res_id:
            continue

        title = html.escape(resource.get('title', ''), quote=True)
        description = html.escape(resource.get('description', ''), quote=True)
        res_type = html.escape(resource.get('type', ''), quote=True)
        access = html.escape(resource.get('access', 'unknown'), quote=True)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
</head>
<body>
    <article data-pagefind-body data-pagefind-meta="title:{title}, type:{res_type}">
        <h1>{title}</h1>
        <p>{description}</p>
        <span data-pagefind-filter="type">{res_type}</span>
        <span data-pagefind-filter="access">{access}</span>
"""
        for tag in resource.get("tags", []):
            safe_tag = html.escape(tag, quote=True)
            html_content += f'        <span data-pagefind-filter="tags">{safe_tag}</span>\n'

        html_content += """    </article>
</body>
</html>"""

        with open(RESOURCES_DIR / f"{res_id}.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        generated += 1

    print(f"Generated {generated} static pages in site/resources/ (skipped {len(resources) - generated} archived)")

if __name__ == "__main__":
    main()
