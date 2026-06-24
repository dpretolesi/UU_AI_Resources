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
SUGGESTIONS_FILE = DATA_DIR / "suggestions.json"
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
    "Never modify resources.json directly; write to data/suggestions.json",
    "Always validate against schema before proposing",
    "Never propose a URL already in resources.json or rejected.json",
    "Respect rate limits between API calls",
    "Cap proposals at MAX_PROPOSALS_PER_RUN",
    "Always update state.json after a run",
    "Log all decisions to agent/logs/",
    "Support DRY_RUN mode for testing",
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
    """Rebuild the set of known URL hashes from resources.json, rejected.json, and suggestions.json."""
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

    # From suggestions
    if SUGGESTIONS_FILE.exists():
        try:
            suggestions = load_json(SUGGESTIONS_FILE)
            for s in suggestions:
                if "url" in s:
                    hashes.add(url_hash(s["url"]))
        except (json.JSONDecodeError, KeyError):
            pass

    return hashes


def compute_reward_profile() -> dict[str, float]:
    """Compute a reward profile for tags based on accepted and rejected resources."""
    reward_profile: dict[str, float] = {}

    # Positive rewards from accepted resources added by the agent
    resources_path = DATA_DIR / "resources.json"
    if resources_path.exists():
        resources = load_json(resources_path)
        for r in resources:
            if r.get("added_by") == "agent":
                for tag in r.get("tags", []):
                    reward_profile[tag] = reward_profile.get(tag, 0.0) + 1.0
            else:
                # Small positive signal for generally accepted topics
                for tag in r.get("tags", []):
                    reward_profile[tag] = reward_profile.get(tag, 0.0) + 0.1

    # Negative rewards from rejected resources
    rejected_path = DATA_DIR / "rejected.json"
    if rejected_path.exists():
        rejected = load_json(rejected_path)
        for entry in rejected.get("rejections", []):
            for tag in entry.get("tags", []):
                reward_profile[tag] = reward_profile.get(tag, 0.0) - 1.0

    return reward_profile


def generate_dynamic_queries(reward_profile: dict[str, float], all_queries: list[str]) -> list[str]:
    """Generate dynamic search queries using Ollama and the reward profile."""
    # Find the top 10 most rewarded tags
    top_tags = sorted(reward_profile.items(), key=lambda x: x[1], reverse=True)[:10]
    top_tag_names = [t[0] for t in top_tags if t[1] > 0]

    # Find the 5 most penalized tags
    bottom_tags = sorted(reward_profile.items(), key=lambda x: x[1])[:5]
    penalized_tags = [t[0] for t in bottom_tags if t[1] < 0]

    if not top_tag_names:
        return []

    try:
        import ollama
        import os

        # Initialize client with API key if available
        headers = {}
        api_key = os.environ.get("OLLAMA_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"), headers=headers)

        prompt = (
            "You are an AI research assistant tasked with discovering high-quality machine learning, AI and GenAI resources for academics and researchers. "
            "Based on past successes, the user is most interested in these topics/tags:\n"
            f"{', '.join(top_tag_names)}\n\n"
        )
        if penalized_tags:
            prompt += (
                "The user explicitly DISLIKES or REJECTED these topics:\n"
                f"{', '.join(penalized_tags)}\n\n"
            )
            
        prompt += (
            "Generate 3 highly specific, novel Google search queries to find research papers, tools, blogposts, videos, podcasts or tutorials that align with the successful topics. "
            "Return ONLY a valid JSON list of strings. Example: [\"state-of-the-art transformer NLP GitHub\", \"new reinforcement learning tutorials 2024\"]\n"
            "Do not include any other text."
        )

        response = client.chat(
            model="gemma4:12b-it-qat",
            messages=[{"role": "user", "content": prompt}],
        )

        content = response['message']['content'].strip()
        # Attempt to parse JSON
        # Clean up markdown code blocks if any
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        dynamic_queries = json.loads(content)
        if isinstance(dynamic_queries, list) and all(isinstance(q, str) for q in dynamic_queries):
            logger.info(f"Generated dynamic queries via LLM: {dynamic_queries}")
            return dynamic_queries[:3]

    except Exception as e:
        logger.warning(f"Failed to generate dynamic queries with LLM: {e}")

    # Fallback heuristic
    import random
    fallback_queries = []
    base_suffixes = ["research papers 2024", "open source GitHub", "tutorial advanced"]
    for i in range(min(3, len(top_tag_names))):
        tag = random.choice(top_tag_names)
        suffix = random.choice(base_suffixes)
        fallback_queries.append(f"{tag.replace('-', ' ')} {suffix}")
    
    logger.info(f"Using heuristic dynamic queries: {fallback_queries}")
    return fallback_queries


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
        ("library", ["library", "package", "pip install", "npm install"]),
        ("framework", ["framework"]),
        ("tool", ["tool", "app", "platform", "service"]),
        ("blog", ["blog", "post", "article"]),
        ("book", ["book", "textbook", "ebook"]),
        ("podcast", ["podcast", "episode"]),
        ("newsletter", ["newsletter", "subscribe"]),
        ("community", ["community", "forum", "discord", "slack"]),
    ]

    for rtype, keywords in type_signals:
        if any(kw in combined for kw in keywords):
            return rtype

    return "tool"


# ---------------------------------------------------------------------------
# GitHub commit creation
# ---------------------------------------------------------------------------


def commit_suggestions_to_main(all_suggestions: list[dict], new_count: int) -> Optional[str]:
    """Commit the updated suggestions.json directly to the default branch."""
    if DRY_RUN:
        logger.info("[DRY_RUN] Would commit %d new proposals", new_count)
        return None

    token = os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo_name:
        logger.warning(
            "GITHUB_TOKEN or GITHUB_REPOSITORY not set; skipping GitHub commit"
        )
        return None

    from github import Github, GithubException

    gh = Github(token)
    repo = gh.get_repo(repo_name)

    content = json.dumps(all_suggestions, indent=2, ensure_ascii=False) + "\n"
    file_path = "data/suggestions.json"
    commit_message = f"🤖 Add {new_count} new AI research resource suggestions"

    try:
        # Get existing file to get its SHA
        try:
            file_contents = repo.get_contents(file_path)
            repo.update_file(
                path=file_path,
                message=commit_message,
                content=content,
                sha=file_contents.sha,
            )
        except GithubException as e:
            if e.status == 404:
                repo.create_file(
                    path=file_path,
                    message=commit_message,
                    content=content,
                )
            else:
                raise
        logger.info(f"Committed {file_path} to repository")
        return f"https://github.com/{repo_name}/commits/{repo.default_branch}"
    except Exception as e:
        logger.error(f"Failed to commit suggestions to GitHub: {e}")
        return None


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

    # Select static queries using rotation cursor
    rotation_idx = state.get("queries_rotation_index", 0) % len(all_queries)
    static_queries = []
    # Use 2 static queries for exploration
    for i in range(2):
        idx = (rotation_idx + i) % len(all_queries)
        static_queries.append(all_queries[idx])
    new_rotation_idx = (rotation_idx + 2) % len(all_queries)
    state["queries_rotation_index"] = new_rotation_idx

    # --- Compute reward profile and dynamic queries ---
    reward_profile = compute_reward_profile()
    logger.info(f"Computed reward profile for {len(reward_profile)} tags")
    
    dynamic_queries = generate_dynamic_queries(reward_profile, all_queries)
    
    selected_queries = static_queries + dynamic_queries
    logger.info(f"Selected mixed queries: {selected_queries}")

    # --- Search and collect candidates ---
    all_candidates: list[dict] = []

    for i, query in enumerate(selected_queries):
        logger.info(f"Searching [{i + 1}/{len(selected_queries)}]: {query}")
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
                reward_profile=reward_profile,
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

    # --- Update suggestions.json ---
    commit_url = None
    if proposals:
        existing_suggestions = []
        if SUGGESTIONS_FILE.exists():
            existing_suggestions = load_json(SUGGESTIONS_FILE)
            if not isinstance(existing_suggestions, list):
                existing_suggestions = []
        
        existing_suggestions.extend(proposals)
        save_json(SUGGESTIONS_FILE, existing_suggestions)
        logger.info(f"Appended {len(proposals)} proposals to suggestions.json")

        # --- Commit to main ---
        commit_url = commit_suggestions_to_main(existing_suggestions, len(proposals))
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
    logger.info(f"  Commit URL: {commit_url or 'N/A'}")
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
