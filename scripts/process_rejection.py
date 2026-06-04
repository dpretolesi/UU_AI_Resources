#!/usr/bin/env python3
"""
Process REJECT: comments from GitHub PR reviews.

Parses the COMMENT_BODY env var for rejection commands, removes the
corresponding pending file from the PR branch, adds the URL to rejected.json,
and posts a confirmation comment via the GitHub API.

Expected COMMENT_BODY format:
    REJECT: https://example.com/resource | Reason for rejection

Environment variables:
    COMMENT_BODY     — The PR comment body containing REJECT commands
    GITHUB_TOKEN     — GitHub PAT for API calls
    GITHUB_REPOSITORY — owner/repo
    PR_NUMBER        — Pull request number
    PR_BRANCH        — Branch name of the PR
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REJECTED_PATH = DATA_DIR / "rejected.json"
PENDING_DIR = DATA_DIR / "pending"

# Pattern: REJECT: <url> | <reason>
REJECT_PATTERN = re.compile(
    r"REJECT:\s*(https?://\S+)\s*\|\s*(.+)", re.IGNORECASE | re.MULTILINE
)


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def parse_rejections(comment_body: str) -> list[tuple[str, str]]:
    """Parse REJECT: commands from a comment body."""
    matches = REJECT_PATTERN.findall(comment_body)
    return [(url.strip(), reason.strip()) for url, reason in matches]


def find_pending_file_for_url(url: str) -> Path | None:
    """Find the pending JSON file that contains the given URL."""
    if not PENDING_DIR.exists():
        return None

    target_hash = url_hash(url)
    for pending_file in PENDING_DIR.glob("*.json"):
        try:
            data = load_json(pending_file)
            if url_hash(data.get("url", "")) == target_hash:
                return pending_file
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def add_to_rejected(url: str, reason: str, resource_title: str = "") -> None:
    """Add a URL to the rejected.json file."""
    if REJECTED_PATH.exists():
        rejected_data = load_json(REJECTED_PATH)
    else:
        rejected_data = {
            "version": 1,
            "description": "Permanent rejection log for AI Research Hub resources.",
            "rejections": [],
        }

    rejection_entry = {
        "url": url,
        "url_hash": url_hash(url),
        "reason": reason,
        "rejected_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "rejected_by": "human",
    }
    if resource_title:
        rejection_entry["title"] = resource_title

    rejected_data["rejections"].append(rejection_entry)
    save_json(REJECTED_PATH, rejected_data)


def remove_pending_from_branch(
    pending_filename: str, branch: str, repo_name: str, token: str
) -> bool:
    """Remove a pending file from the PR branch via GitHub API."""
    try:
        from github import Github, GithubException

        gh = Github(token)
        repo = gh.get_repo(repo_name)
        file_path = f"data/pending/{pending_filename}"

        try:
            contents = repo.get_contents(file_path, ref=branch)
            repo.delete_file(
                path=file_path,
                message=f"Reject resource: {pending_filename}",
                sha=contents.sha,
                branch=branch,
            )
            print(f"  Removed {file_path} from branch {branch}")
            return True
        except GithubException as e:
            print(f"  WARNING: Could not remove {file_path}: {e}")
            return False

    except ImportError:
        print("  WARNING: PyGithub not installed; skipping branch file removal")
        return False


def post_confirmation_comment(
    pr_number: int,
    rejections: list[tuple[str, str]],
    repo_name: str,
    token: str,
) -> None:
    """Post a confirmation comment on the PR."""
    try:
        from github import Github

        gh = Github(token)
        repo = gh.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        lines = ["## ❌ Resources Rejected\n"]
        for url, reason in rejections:
            lines.append(f"- **{url}**")
            lines.append(f"  Reason: {reason}\n")
        lines.append(
            f"\n*Processed at {datetime.now(timezone.utc).isoformat()}*"
        )

        pr.create_issue_comment("\n".join(lines))
        print(f"  Posted confirmation comment on PR #{pr_number}")

    except ImportError:
        print("  WARNING: PyGithub not installed; skipping comment")
    except Exception as e:
        print(f"  WARNING: Failed to post comment: {e}")


def main() -> int:
    comment_body = os.environ.get("COMMENT_BODY", "")
    if not comment_body:
        print("ERROR: COMMENT_BODY environment variable is empty or not set.")
        return 1

    rejections = parse_rejections(comment_body)
    if not rejections:
        print("No REJECT: commands found in comment body.")
        return 0

    print(f"Found {len(rejections)} rejection(s) to process:\n")

    token = os.environ.get("GITHUB_TOKEN", "")
    repo_name = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number_str = os.environ.get("PR_NUMBER", "")
    pr_branch = os.environ.get("PR_BRANCH", "")

    processed = 0
    for url, reason in rejections:
        print(f"Processing rejection: {url}")
        print(f"  Reason: {reason}")

        # Find and process the pending file
        pending_file = find_pending_file_for_url(url)
        resource_title = ""
        if pending_file:
            try:
                data = load_json(pending_file)
                resource_title = data.get("title", "")
            except (json.JSONDecodeError, KeyError):
                pass

            # Remove from local pending directory
            pending_file.unlink()
            print(f"  Removed local pending file: {pending_file.name}")

            # Remove from PR branch
            if token and repo_name and pr_branch:
                remove_pending_from_branch(
                    pending_file.name, pr_branch, repo_name, token
                )
        else:
            print(f"  WARNING: No pending file found for URL: {url}")

        # Add to rejected.json
        add_to_rejected(url, reason, resource_title)
        print(f"  Added to rejected.json")
        processed += 1

    # Post confirmation comment
    if token and repo_name and pr_number_str:
        try:
            pr_number = int(pr_number_str)
            post_confirmation_comment(pr_number, rejections, repo_name, token)
        except ValueError:
            print(f"  WARNING: Invalid PR_NUMBER: {pr_number_str}")

    print(f"\nProcessed {processed}/{len(rejections)} rejections.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
