#!/usr/bin/env python3
"""
AI Research Hub — Crawl Agent

Discovers, scores, and proposes new AI/ML resources for the hub.
Runs as a scheduled agent (e.g., weekly via GitHub Actions).

Environment variables:
  GITHUB_TOKEN        — GitHub Personal Access Token (required for PR creation)
  GITHUB_REPOSITORY   — owner/repo (required for PR creation)
  SEARCH_BACKEND      — tavily | serper | duckduckgo (default: tavily)
  TAVILY_API_KEY      — Tavily API key (required if backend=tavily)
  SERPER_API_KEY       — Serper API key (required if backend=serper)
  OLLAMA_API_KEY      — Ollama API key (optional, for LLM scoring)
  DRY_RUN             — If "true", skip PR creation and GitHub interactions
  MIN_QUALITY_SCORE   — Minimum quality score threshold (default: 6.0)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
AGENT_DIR = PROJECT_ROOT / "agent"
PENDING_DIR = DATA_DIR / "pending"
LOG_DIR = AGENT_DIR / "logs"

sys.path.insert(0, str(AGENT_DIR))

import quality_filter  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PROPOSALS_PER_RUN = 20
MIN_PROPOSALS_TO_OPEN_PR = 3
SEARCH_RATE_LIMIT_SECONDS = 1.0
FETCH_RATE_LIMIT_SECONDS = 0.5
MIN_QUALITY_SCORE = float(os.environ.get("MIN_QUALITY_SCORE", "6.0"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "tavily").lower()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = datetime.now(timezone.utc).strftime("crawl_%Y%m%d_%H%M%S.log")
log_filepath = LOG_DIR / log_filename

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_filepath, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("crawl_agent")

# ---------------------------------------------------------------------------
# Behavioral rules (enforced via assertions)
# ---------------------------------------------------------------------------

BEHAVIORAL_RULES = [
    "Never modify resources.json directly; write to data/pending/",
    "Always validate against schema before proposing",
    "Never propose a URL already in resources.json or rejected.json",
    "Respect rate limits between API calls",
    "Cap proposals at MAX_PROPOSALS_PER_RUN",
    "Require MIN_PROPOSALS_TO_OPEN_PR before creating a PR",
    "Always update state.json after a run",
    "Log all decisions to agent/logs/",
    "Support DRY_RUN mode for testing",
    "Check branch existence for idempotency",
]

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def url_hash(url: str) -> str:
    """Compute a truncated SHA-256 hash of a URL for deduplication."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def load_json(path: Path) -> Any:
    """Load and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    logger.debug(f"Saved {path}")


def load_state() -> dict:
    """Load agent state from state.json."""
    state_path = AGENT_DIR / "state.json"
    if state_path.exists():
        return load_json(state_path)
    return {
        "last_run_utc": None,
        "total_proposed": 0,
        "total_accepted": 0,
        "total_rejected": 0,
        "queries_rotation_index": 0,
        "known_url_hashes": [],
    }


def save_state(state: dict) -> None:
    """Persist agent state to state.json."""
    save_json(AGENT_DIR / "state.json", state)


def rebuild_known_hashes() -> set[str]:
    """Rebuild the set of known URL hashes from resources.json and rejected.json."""
    hashes: set[str] = set()

    # From resources
    resources_path = DATA_DIR / "resources.json"
    if resources_path.exists():
        resources = load_json(resources_path)
        for r in resources:
            hashes.add(url_hash(r["url"]))

    # From rejections
    rejected_path = DATA_DIR / "rejected.json"
    if rejected_path.exists():
        rejected = load_json(rejected_path)
        for entry in rejected.get("rejections", []):
            if "url" in entry:
                hashes.add(url_hash(entry["url"]))

    # From pending
    if PENDING_DIR.exists():
        for pending_file in PENDING_DIR.glob("*.json"):
            try:
                pending = load_json(pending_file)
                hashes.add(url_hash(pending["url"]))
            except (json.JSONDecodeError, KeyError):
                pass

    return hashes


def generate_resource_id(url: str) -> str:
    """Generate a deterministic resource ID from a URL."""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"auto-{h}"


def validate_resource(resource: dict) -> list[str]:
    """Validate a resource against the schema. Returns a list of errors."""
    try:
        import jsonschema
    except ImportError:
        logger.warning("jsonschema not installed; skipping validation")
        return []

    schema_path = DATA_DIR / "schema.json"
    if not schema_path.exists():
        return ["schema.json not found"]

    schema = load_json(schema_path)
    validator = jsonschema.Draft7Validator(schema)
    return [e.message for e in validator.iter_errors(resource)]


# ---------------------------------------------------------------------------
# Search backends
# ---------------------------------------------------------------------------


def search_tavily(query: str, max_results: int = 10) -> list[dict]:
    """Search using the Tavily API."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable is not set")

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_domains=[],
        exclude_domains=list(quality_filter.BLACKLISTED_DOMAINS),
    )
    results = []
    for item in response.get("results", []):
        results.append(
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "description": item.get("content", ""),
            }
        )
    return results


def search_serper(query: str, max_results: int = 10) -> list[dict]:
    """Search using the Serper API."""
    import requests

    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise RuntimeError("SERPER_API_KEY environment variable is not set")

    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": max_results},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append(
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "description": item.get("snippet", ""),
            }
        )
    return results


def search_duckduckgo(query: str, max_results: int = 10) -> list[dict]:
    """Search using DuckDuckGo (no API key required)."""
    import requests

    response = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("RelatedTopics", [])[:max_results]:
        if "FirstURL" in item and "Text" in item:
            results.append(
                {
                    "url": item["FirstURL"],
                    "title": item.get("Text", "")[:200],
                    "description": item.get("Text", ""),
                }
            )
    return results


SEARCH_BACKENDS = {
    "tavily": search_tavily,
    "serper": search_serper,
    "duckduckgo": search_duckduckgo,
}


def do_search(query: str, max_results: int = 10) -> list[dict]:
    """Execute a search using the configured backend."""
    backend_fn = SEARCH_BACKENDS.get(SEARCH_BACKEND)
    if not backend_fn:
        raise ValueError(
            f"Unknown SEARCH_BACKEND: {SEARCH_BACKEND}. "
            f"Supported: {', '.join(SEARCH_BACKENDS.keys())}"
        )
    return backend_fn(query, max_results)


# ---------------------------------------------------------------------------
# Page fetching & metadata enrichment
# ---------------------------------------------------------------------------


def fetch_page_metadata(url: str) -> dict[str, Any]:
    """Fetch a page and extract metadata for enrichment."""
    import requests
    from bs4 import BeautifulSoup

    metadata: dict[str, Any] = {}
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AIResearchHubBot/1.0; "
                    "+https://github.com/ai-research-hub)"
                )
            },
            allow_redirects=True,
        )
        if response.status_code >= 400:
            metadata["is_broken"] = True
            return metadata

        metadata["is_broken"] = False
        soup = BeautifulSoup(response.text, "lxml")

        # Extract title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            metadata["title"] = og_title["content"].strip()
        elif soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()

        # Extract description
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc and og_desc.get("content"):
            metadata["description"] = og_desc["content"].strip()
        elif meta_desc and meta_desc.get("content"):
            metadata["description"] = meta_desc["content"].strip()

        # Extract authors
        author_meta = soup.find("meta", attrs={"name": "author"})
        if author_meta and author_meta.get("content"):
            metadata["authors"] = [
                a.strip() for a in author_meta["content"].split(",")
            ]

        # Detect language
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            lang = html_tag["lang"][:2].lower()
            if len(lang) == 2 and lang.isalpha():
                metadata["language"] = lang

    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        metadata["is_broken"] = True
    except Exception as e:
        logger.warning(f"Error parsing {url}: {e}")

    return metadata


def enrich_resource(
    raw: dict, resource_type: str = "tool"
) -> dict[str, Any]:
    """
    Enrich a raw search result into a full resource record.
    Fills all schema fields with best-effort data.
    """
    url = raw["url"]
    title = raw.get("title", "")
    description = raw.get("description", "")

    # Fetch page metadata for enrichment
    page_meta = fetch_page_metadata(url)

    # Prefer page metadata over search result data
    if page_meta.get("title") and len(page_meta["title"]) > len(title):
        title = page_meta["title"]
    if page_meta.get("description") and len(page_meta.get("description", "")) > len(
        description
    ):
        description = page_meta["description"]

    # Ensure title length
    if len(title) < 5:
        title = f"Resource: {url[:100]}"
    title = title[:200]

    # Ensure description length
    if len(description) < 30:
        description = f"AI/ML resource discovered at {url}. Visit the link for detailed information about this resource."
    description = description[:800]

    # Generate tags from title and description
    tags = _generate_tags(title, description, resource_type)

    resource = {
        "id": generate_resource_id(url),
        "title": title,
        "url": url,
        "type": resource_type,
        "tags": tags,
        "description": description,
        "added_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "added_by": "agent",
        "language": page_meta.get("language", "en"),
        "access": "unknown",
        "archived": False,
    }

    if page_meta.get("authors"):
        resource["authors"] = page_meta["authors"]

    current_year = datetime.now(timezone.utc).year
    resource["year"] = current_year

    return resource


def _generate_tags(title: str, description: str, resource_type: str) -> list[str]:
    """Generate relevant tags from title and description text."""
    tag_candidates = {
        "deep-learning": ["deep learning", "deep neural"],
        "machine-learning": ["machine learning", "ml model"],
        "nlp": ["natural language", "nlp", "language model", "text processing"],
        "computer-vision": ["computer vision", "image recognition", "object detection"],
        "transformers": ["transformer", "attention mechanism"],
        "reinforcement-learning": ["reinforcement learning", "rl agent", "reward"],
        "generative-ai": ["generative", "diffusion", "gan", "variational"],
        "llm": ["large language model", "llm", "gpt", "chatgpt"],
        "pytorch": ["pytorch"],
        "tensorflow": ["tensorflow"],
        "python": ["python"],
        "research": ["research", "paper", "study", "arxiv"],
        "tutorial": ["tutorial", "guide", "how to", "walkthrough"],
        "open-source": ["open source", "open-source", "github"],
        "benchmark": ["benchmark", "evaluation", "leaderboard"],
        "dataset": ["dataset", "data set", "corpus"],
        "fine-tuning": ["fine-tuning", "fine tuning", "finetune"],
        "rag": ["retrieval augmented", "rag"],
        "neural-networks": ["neural network"],
        "optimization": ["optimization", "optimizer"],
    }

    combined = f"{title} {description}".lower()
    tags: list[str] = []

    for tag, keywords in tag_candidates.items():
        if any(kw in combined for kw in keywords):
            tags.append(tag)
        if len(tags) >= 9:
            break

    # Always include the resource type as a tag if space permits
    type_tag = resource_type.replace("_", "-")
    if type_tag not in tags and len(tags) < 10:
        tags.append(type_tag)

    # Ensure at least 1 tag
    if not tags:
        tags = ["ai"]

    return tags[:10]


def _infer_resource_type(url: str, title: str, description: str) -> str:
    """Infer the resource type from URL and content."""
    combined = f"{url} {title} {description}".lower()

    type_signals = [
        ("paper", ["arxiv.org", "paper", "proceedings", "conference", "journal"]),
        ("course", ["course", "syllabus", "lecture", "curriculum", "class"]),
        ("tutorial", ["tutorial", "guide", "how to", "step by step", "walkthrough"]),
        ("video", ["youtube.com", "video", "watch", "playlist"]),
        ("dataset", ["dataset", "data set", "corpus", "benchmark data"]),
        ("library", ["library", "package", "pip install", "npm install"]),
        ("framework", ["framework"]),
        ("tool", ["tool", "app", "platform", "service"]),
        ("blog", ["blog", "post", "article"]),
        ("book", ["book", "textbook", "ebook"]),
        ("podcast", ["podcast", "episode"]),
        ("newsletter", ["newsletter", "subscribe"]),
        ("model", ["model", "weights", "checkpoint", "pretrained"]),
        ("benchmark", ["benchmark", "leaderboard", "evaluation"]),
        ("community", ["community", "forum", "discord", "slack"]),
    ]

    for rtype, keywords in type_signals:
        if any(kw in combined for kw in keywords):
            return rtype

    return "tool"


# ---------------------------------------------------------------------------
# GitHub PR creation
# ---------------------------------------------------------------------------


def create_github_pr(proposals: list[dict], branch_name: str) -> Optional[str]:
    """Create a GitHub PR with the proposed resources."""
    if DRY_RUN:
        logger.info("[DRY_RUN] Would create PR with %d proposals", len(proposals))
        return None

    token = os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo_name:
        logger.warning(
            "GITHUB_TOKEN or GITHUB_REPOSITORY not set; skipping PR creation"
        )
        return None

    from github import Github, GithubException

    gh = Github(token)
    repo = gh.get_repo(repo_name)

    # Check if branch already exists (idempotency)
    try:
        repo.get_branch(branch_name)
        logger.info(f"Branch '{branch_name}' already exists; skipping PR creation")
        return None
    except GithubException as e:
        if e.status != 404:
            raise

    # Create branch from default branch
    default_branch = repo.default_branch
    ref = repo.get_git_ref(f"heads/{default_branch}")
    sha = ref.object.sha
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=sha)
    logger.info(f"Created branch: {branch_name}")

    # Add pending files to the branch
    for proposal in proposals:
        file_path = f"data/pending/{proposal['id']}.json"
        content = json.dumps(proposal, indent=2, ensure_ascii=False)
        repo.create_file(
            path=file_path,
            message=f"Add pending resource: {proposal['title'][:60]}",
            content=content,
            branch=branch_name,
        )
        logger.info(f"Added {file_path} to branch")

    # Build PR body with markdown table
    table_rows = []
    for p in proposals:
        tags_str = ", ".join(p.get("tags", [])[:3])
        table_rows.append(
            f"| [{p['title'][:50]}]({p['url']}) | {p['type']} | {tags_str} | "
            f"{p.get('quality_score', 'N/A')} |"
        )

    pr_body = (
        "## 🤖 AI Research Hub — New Resource Proposals\n\n"
        f"The crawl agent discovered **{len(proposals)}** new resources.\n\n"
        "### Proposed Resources\n\n"
        "| Title | Type | Tags | Score |\n"
        "|-------|------|------|-------|\n"
        + "\n".join(table_rows)
        + "\n\n"
        "### Review Instructions\n\n"
        "- **Approve & merge** to accept all proposals\n"
        "- **Comment** `REJECT: <url> | <reason>` on any resource to reject it\n"
        "- Rejected resources are permanently added to `data/rejected.json`\n\n"
        f"*Generated at {datetime.now(timezone.utc).isoformat()}*"
    )

    pr = repo.create_pull(
        title=f"🤖 Add {len(proposals)} new AI research resources",
        body=pr_body,
        head=branch_name,
        base=default_branch,
    )
    logger.info(f"Created PR #{pr.number}: {pr.html_url}")
    return pr.html_url


# ---------------------------------------------------------------------------
# Main crawl pipeline
# ---------------------------------------------------------------------------


def run_crawl() -> None:
    """Execute the full crawl pipeline."""
    logger.info("=" * 60)
    logger.info("AI Research Hub — Crawl Agent Starting")
    logger.info(f"DRY_RUN={DRY_RUN}, SEARCH_BACKEND={SEARCH_BACKEND}")
    logger.info(f"MIN_QUALITY_SCORE={MIN_QUALITY_SCORE}")
    logger.info("=" * 60)

    # --- Load state ---
    state = load_state()
    logger.info(f"Loaded state: {json.dumps(state, indent=2)}")

    # --- Rebuild known URL hashes ---
    known_hashes = rebuild_known_hashes()
    logger.info(f"Known URL hashes: {len(known_hashes)}")

    # Rule: Always update state with known hashes
    state["known_url_hashes"] = sorted(known_hashes)

    # --- Load search queries ---
    queries_path = AGENT_DIR / "search_queries.json"
    all_queries = load_json(queries_path)
    assert isinstance(all_queries, list) and len(all_queries) > 0, (
        "search_queries.json must be a non-empty list"
    )

    # Select 5 queries using rotation cursor
    rotation_idx = state.get("queries_rotation_index", 0) % len(all_queries)
    selected_queries = []
    for i in range(5):
        idx = (rotation_idx + i) % len(all_queries)
        selected_queries.append(all_queries[idx])
    new_rotation_idx = (rotation_idx + 5) % len(all_queries)
    state["queries_rotation_index"] = new_rotation_idx
    logger.info(f"Selected queries (idx {rotation_idx}-{rotation_idx + 4}): {selected_queries}")

    # --- Search and collect candidates ---
    all_candidates: list[dict] = []

    for i, query in enumerate(selected_queries):
        logger.info(f"Searching [{i + 1}/5]: {query}")
        try:
            results = do_search(query, max_results=10)
            logger.info(f"  -> {len(results)} results")
            all_candidates.extend(results)
        except Exception as e:
            logger.error(f"  -> Search failed: {e}")

        # Rate limiting between search calls
        if i < len(selected_queries) - 1:
            time.sleep(SEARCH_RATE_LIMIT_SECONDS)

    logger.info(f"Total candidates from search: {len(all_candidates)}")

    # --- Deduplicate, score, and enrich ---
    proposals: list[dict] = []
    seen_urls_this_run: set[str] = set()

    for candidate in all_candidates:
        url = candidate.get("url", "").strip()
        if not url:
            continue

        # Dedup within this run
        if url in seen_urls_this_run:
            continue
        seen_urls_this_run.add(url)

        # Dedup against known hashes
        h = url_hash(url)
        if h in known_hashes:
            logger.debug(f"Skipping known URL: {url}")
            continue

        # Infer resource type
        resource_type = _infer_resource_type(
            url, candidate.get("title", ""), candidate.get("description", "")
        )

        # Score the candidate
        title = candidate.get("title", "")
        description = candidate.get("description", "")

        try:
            score, breakdown = quality_filter.score_resource(
                url=url,
                title=title,
                description=description,
                resource_type=resource_type,
                use_llm_fallback=not DRY_RUN,
            )
        except quality_filter.QualityRejectionError as e:
            logger.info(f"Hard-rejected: {url} — {e.reason}")
            known_hashes.add(h)
            continue

        if not quality_filter.is_acceptable(score, MIN_QUALITY_SCORE):
            logger.info(f"Below threshold ({score:.1f}): {url}")
            continue

        # Rate limit page fetches
        time.sleep(FETCH_RATE_LIMIT_SECONDS)

        # Enrich metadata
        resource = enrich_resource(candidate, resource_type)
        resource["quality_score"] = round(score, 2)

        # Validate against schema
        errors = validate_resource(resource)
        if errors:
            logger.warning(f"Schema validation failed for {url}: {errors}")
            continue

        proposals.append(resource)
        known_hashes.add(h)
        logger.info(
            f"Proposal accepted: {resource['title'][:60]} (score={score:.1f})"
        )

        # Cap proposals
        # Rule: Cap proposals at MAX_PROPOSALS_PER_RUN
        assert len(proposals) <= MAX_PROPOSALS_PER_RUN, (
            f"Exceeded MAX_PROPOSALS_PER_RUN ({MAX_PROPOSALS_PER_RUN})"
        )
        if len(proposals) >= MAX_PROPOSALS_PER_RUN:
            logger.info(f"Reached MAX_PROPOSALS_PER_RUN ({MAX_PROPOSALS_PER_RUN})")
            break

    logger.info(f"Total proposals: {len(proposals)}")

    # --- Write pending files ---
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    for proposal in proposals:
        pending_path = PENDING_DIR / f"{proposal['id']}.json"
        # Rule: Never modify resources.json directly; write to data/pending/
        save_json(pending_path, proposal)
        logger.info(f"Wrote pending: {pending_path.name}")

    # --- Create GitHub PR if enough proposals ---
    pr_url = None
    if len(proposals) >= MIN_PROPOSALS_TO_OPEN_PR:
        branch_name = (
            f"crawl/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )
        pr_url = create_github_pr(proposals, branch_name)
    elif len(proposals) > 0:
        logger.info(
            f"Only {len(proposals)} proposals (need {MIN_PROPOSALS_TO_OPEN_PR}); "
            f"skipping PR creation. Files saved to data/pending/."
        )
    else:
        logger.info("No proposals this run.")

    # --- Update state ---
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    state["total_proposed"] = state.get("total_proposed", 0) + len(proposals)
    state["known_url_hashes"] = sorted(known_hashes)
    save_state(state)
    logger.info("State updated.")

    # --- Summary ---
    logger.info("=" * 60)
    logger.info("Crawl Agent Run Complete")
    logger.info(f"  Proposals: {len(proposals)}")
    logger.info(f"  PR URL: {pr_url or 'N/A'}")
    logger.info(f"  Known hashes: {len(known_hashes)}")
    logger.info(f"  Log file: {log_filepath}")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_crawl()
    except KeyboardInterrupt:
        logger.info("Crawl agent interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Crawl agent failed: {e}")
        sys.exit(1)
