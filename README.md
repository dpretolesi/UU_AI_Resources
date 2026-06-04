# AI Research Hub

[![Resources](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2F{owner}%2F{repo}%2Fmain%2Fdata%2Fstats.json&query=%24.total_resources&label=resources&color=blue)](data/resources.json)
[![Last Updated](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2F{owner}%2F{repo}%2Fmain%2Fdata%2Fstats.json&query=%24.last_updated&label=last%20updated&color=green)](data/resources.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A curated, AI-maintained collection of high-quality artificial intelligence research resources. An autonomous agent crawls the web twice a week to discover new papers, tools, datasets, and educational materials — then opens pull requests for human review.

## Features

- **AI-Powered Discovery** — An autonomous agent crawls academic sources, repositories, and communities to find valuable resources
- **Human-in-the-Loop Review** — Every resource goes through a pull request review before inclusion
- **Full-Text Search** — A statically generated site with [Pagefind](https://pagefind.app/) enables instant client-side search across all resources
- **Quality Scoring** — Resources are scored on relevance, recency, authority, and technical depth
- **Structured Data** — All resources are stored as validated JSON with consistent schema
- **Duplicate Detection** — Automated checks prevent redundant entries
- **Rejection Tracking** — Rejected resources are logged to avoid re-crawling
- **Open Contribution** — Anyone can submit resources via GitHub Issues or pull requests

## Quick Start

### Browse Resources

Visit the **[AI Research Hub site]** to search and browse all indexed resources.

### Submit a Resource

1. **Via Issue Form** — Open a [new resource submission](../../issues/new?template=resource_submission.yml) and fill in the details
2. **Via Pull Request** — Add entries directly to `data/resources.json` and open a PR

### Run Locally

```bash
# Clone the repository
git clone https://github.com/{owner}/{repo}.git
cd {repo}

# Install Python dependencies
pip install -r requirements.txt

# Run the crawl agent manually
export ANTHROPIC_API_KEY="your-key"
export TAVILY_API_KEY="your-key"
python agent/crawl.py

# Build the search site locally
python scripts/generate_resource_pages.py
npx pagefind
```

## Architecture

```
ai-research-hub/
├── agent/                    # AI crawl agent
│   ├── crawl.py              # Main crawl entrypoint
│   ├── prompts/              # Agent prompt templates
│   └── logs/                 # Crawl run logs (gitignored)
├── data/
│   ├── resources.json        # Canonical resource database
│   ├── pending.json          # Resources awaiting review
│   ├── rejected.json         # Rejected resources (to avoid re-crawling)
│   ├── state.json            # Agent state and cursor positions
│   └── schema.json           # JSON Schema for resource validation
├── scripts/
│   ├── validate_schema.py    # Schema validation for PRs
│   ├── check_duplicates.py   # Duplicate detection
│   ├── check_not_rejected.py # Cross-check against rejected list
│   ├── process_pending.py    # Merge pending resources on PR merge
│   ├── process_rejection.py  # Handle REJECT: comments
│   ├── generate_resource_pages.py  # Static page generator
│   └── generate_stats.py     # Compute stats.json for badges
├── site/
│   ├── index.html            # Search interface
│   ├── styles.css            # Site styles
│   └── resources/            # Generated resource pages (gitignored)
├── .github/
│   ├── workflows/            # CI/CD pipelines
│   │   ├── agent-crawl.yml       # Scheduled crawl (Mon + Thu)
│   │   ├── validate-content.yml  # PR validation checks
│   │   ├── build-search-index.yml # Build + deploy site
│   │   ├── reject-handler.yml    # Handle REJECT: comments
│   │   └── process-pending.yml   # Post-merge resource processing
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
│       └── resource_submission.yml
├── pagefind.yml              # Pagefind configuration
├── requirements.txt          # Python dependencies
├── CONTRIBUTING.md           # Contribution guide
├── CONTENT_POLICY.md         # Quality standards
├── LICENSE                   # MIT License
└── README.md                 # This file
```

## How the AI Agent Works

The crawl agent runs on a scheduled GitHub Actions workflow every Monday and Thursday at 08:00 UTC:

1. **Source Discovery** — The agent uses the Tavily search API to find new AI research resources across academic preprint servers (arXiv, bioRxiv), code repositories (GitHub, HuggingFace), educational platforms, and research blogs.

2. **Evaluation** — Each candidate resource is evaluated by the Anthropic Claude API against the project's [Content Policy](CONTENT_POLICY.md). The agent scores resources on relevance, recency, authority, uniqueness, and technical depth.

3. **Deduplication** — Candidate URLs are checked against `data/resources.json` (existing resources) and `data/rejected.json` (previously rejected resources) to avoid duplicates.

4. **PR Creation** — Resources that pass evaluation are added to `data/pending.json`, and the agent opens a pull request with the proposed additions. The PR body lists each resource with its metadata and quality score.

5. **Human Review** — A maintainer reviews the PR. They can approve individual resources or reject them with a `REJECT: <url> | <reason>` comment.

6. **Integration** — When the PR is merged, the `process-pending` workflow moves approved resources into `data/resources.json` and updates the site.

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  Scheduled   │───▶│  AI Agent    │───▶│  Pull        │───▶│  Human   │
│  Trigger     │    │  Crawl       │    │  Request     │    │  Review  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────┘
                                                                │
                          ┌──────────────┐    ┌──────────┐      │
                          │  Site        │◀───│  Merge   │◀─────┘
                          │  Deploy      │    │  & Process│
                          └──────────────┘    └──────────┘
```

## Contributing

We welcome contributions from the community. See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions on:

- Submitting resources via the GitHub Issue form
- Opening pull requests with new resources
- Tag conventions and quality standards
- How the AI crawl pipeline works

## Content Policy

All resources are evaluated against our [Content Policy](CONTENT_POLICY.md), which defines:

- Inclusion and exclusion criteria
- The quality scoring rubric
- Maintenance and review schedule

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
