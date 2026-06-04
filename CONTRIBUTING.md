# Contributing to AI Research Hub

Thank you for your interest in contributing to the AI Research Hub. This guide covers all the ways you can help grow this curated collection of AI research resources.

## Table of Contents

- [For Humans](#for-humans)
  - [GitHub Issue Form](#github-issue-form)
  - [Direct Pull Request](#direct-pull-request)
  - [Resource JSON Format](#resource-json-format)
- [For the AI Agent](#for-the-ai-agent)
- [Tag Conventions](#tag-conventions)
- [Quality Standards](#quality-standards)

---

## For Humans

There are three ways to contribute resources as a human contributor.

### GitHub Issue Form

The easiest way to submit a resource:

1. Go to **Issues → New Issue → Resource Submission**
2. Fill in the required fields:
   - **URL** — The full URL of the resource
   - **Title** — A clear, descriptive title
   - **Type** — Select from the dropdown (paper, tool, dataset, etc.)
   - **Description** — A brief summary of the resource's value
   - **Tags** — Comma-separated relevant tags
   - **Institution** — (Optional) The organization behind the resource
3. Submit the issue. A maintainer will review it and create a PR if it meets our [Content Policy](CONTENT_POLICY.md).

### Direct Pull Request

For contributors comfortable with JSON:

1. Fork the repository
2. Add your resource(s) to `data/pending.json`
3. Ensure each entry matches the [resource schema](#resource-json-format)
4. Run validation locally:
   ```bash
   pip install jsonschema
   python scripts/validate_schema.py
   python scripts/check_duplicates.py
   python scripts/check_not_rejected.py
   ```
5. Open a pull request against `main`
6. Fill in the PR template checklist

### Resource JSON Format

Each resource entry must follow this schema:

```json
{
  "url": "https://arxiv.org/abs/2401.12345",
  "title": "Example Paper Title",
  "type": "paper",
  "description": "A brief description of the resource and its value to researchers.",
  "tags": ["transformers", "nlp", "attention"],
  "date_added": "2025-06-01",
  "source": "human",
  "quality_score": 8.5,
  "metadata": {
    "authors": ["Author One", "Author Two"],
    "institution": "Example University",
    "year": 2025
  }
}
```

**Required fields:** `url`, `title`, `type`, `description`, `tags`, `date_added`, `source`

**Optional fields:** `quality_score`, `metadata`

**Valid types:** `paper`, `tool`, `dataset`, `library`, `framework`, `tutorial`, `course`, `blog`, `video`, `podcast`, `book`, `benchmark`, `model`, `api`, `community`

---

## For the AI Agent

The AI crawl agent runs automatically on a schedule (Monday and Thursday at 08:00 UTC). Here is how the pipeline works:

### Crawl Pipeline

1. **Trigger** — The `agent-crawl.yml` GitHub Actions workflow fires on the cron schedule or via manual dispatch.

2. **Source Scanning** — The agent queries the Tavily search API with curated search terms targeting:
   - Academic preprint servers (arXiv, bioRxiv, medRxiv)
   - Code hosting platforms (GitHub, GitLab, HuggingFace)
   - Research blogs and institutional publications
   - Educational platforms and course aggregators

3. **Candidate Evaluation** — Each discovered URL is sent to the Anthropic Claude API for evaluation against the project's [Content Policy](CONTENT_POLICY.md). The model returns:
   - A quality score (0–10)
   - Extracted metadata (title, type, description, tags)
   - A justification for the score

4. **Filtering** — Resources are filtered based on:
   - Quality score ≥ 6.0
   - Not already in `data/resources.json`
   - Not already in `data/rejected.json`
   - URL is accessible and returns a valid response

5. **PR Creation** — Passing resources are written to `data/pending.json` and a pull request is opened with the full list of proposed additions.

6. **Review & Merge** — Maintainers review, approve, or reject individual resources. On merge, the `process-pending` workflow integrates approved resources into `data/resources.json`.

### Agent State

The agent maintains state in `data/state.json` to track:
- Last crawl timestamp
- Source-specific cursors (e.g., last arXiv ID processed)
- Crawl statistics (resources found, accepted, rejected per run)

---

## Tag Conventions

Tags help users discover resources through search and filtering. Follow these conventions:

### Format Rules

- Use **lowercase** with **hyphens** for multi-word tags: `deep-learning`, not `Deep Learning` or `deep_learning`
- Use **singular form**: `transformer`, not `transformers`
- Keep tags **concise**: prefer `nlp` over `natural-language-processing`
- Apply **2–6 tags** per resource

### Standard Tags by Domain

| Domain | Recommended Tags |
|--------|-----------------|
| Natural Language Processing | `nlp`, `language-model`, `transformer`, `text-generation`, `sentiment-analysis`, `machine-translation`, `tokenization` |
| Computer Vision | `computer-vision`, `image-classification`, `object-detection`, `segmentation`, `generative-model`, `diffusion` |
| Reinforcement Learning | `reinforcement-learning`, `policy-gradient`, `multi-agent`, `reward-model`, `rlhf` |
| Machine Learning Fundamentals | `optimization`, `regularization`, `generalization`, `loss-function`, `neural-architecture` |
| Data & Infrastructure | `dataset`, `benchmark`, `distributed-training`, `mlops`, `data-pipeline` |
| Ethics & Safety | `ai-safety`, `alignment`, `fairness`, `interpretability`, `explainability`, `bias` |
| Multimodal | `multimodal`, `vision-language`, `text-to-image`, `audio`, `speech` |
| Agents & Reasoning | `agent`, `reasoning`, `chain-of-thought`, `tool-use`, `planning` |

### Special Tags

- `foundational` — Seminal papers or tools that define a field
- `survey` — Review papers or comprehensive overviews
- `sota` — Resources presenting state-of-the-art results
- `beginner-friendly` — Suitable for newcomers to the field
- `production` — Tools and practices for production deployment

---

## Quality Standards

All submitted resources are evaluated against the criteria defined in [CONTENT_POLICY.md](CONTENT_POLICY.md). Key requirements:

- **Relevance** — Must be directly related to AI/ML research or practice
- **Quality Score ≥ 6.0** — Resources must meet the minimum quality threshold
- **No Duplicates** — The resource must not already exist in the database
- **Accessible** — The URL must be publicly accessible (no paywalled content without free alternatives)
- **Not Promotional** — Resources must provide genuine educational or research value, not serve as marketing

For the full scoring rubric and exclusion criteria, see [CONTENT_POLICY.md](CONTENT_POLICY.md).

---

## Questions?

If you have questions about contributing, open a [discussion](../../discussions) or file an issue. We appreciate every contribution that helps build a better resource for the AI research community.
