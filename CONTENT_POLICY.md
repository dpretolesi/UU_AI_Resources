# Content Policy

This document defines the quality standards, inclusion criteria, and review process for resources in the AI Research Hub. Both the AI crawl agent and human reviewers use these guidelines to evaluate candidate resources.

## Table of Contents

- [Inclusion Criteria](#inclusion-criteria)
- [Exclusion Criteria](#exclusion-criteria)
- [Scoring Rubric](#scoring-rubric)
- [Review Process](#review-process)
- [Maintenance Schedule](#maintenance-schedule)

---

## Inclusion Criteria

A resource must meet **all** of the following criteria to be included:

### 1. Relevance
- The resource must be directly related to artificial intelligence, machine learning, deep learning, or closely adjacent fields (e.g., computational neuroscience, AI ethics, MLOps)
- It must provide value to AI researchers, practitioners, or students

### 2. Quality
- The resource must achieve a **quality score of 6.0 or higher** on the scoring rubric (see below)
- Content must be technically accurate and well-presented

### 3. Accessibility
- The resource URL must be publicly accessible
- If the primary content is paywalled, a free preprint or open-access version must be available (e.g., arXiv for conference papers)
- Resources must be available in English (bilingual resources with English content are acceptable)

### 4. Uniqueness
- The resource must not duplicate an existing entry in `data/resources.json`
- If a resource is a substantial update or new version of an existing entry, both may coexist with clear version indicators

### 5. Persistence
- The resource should be hosted on a stable platform with reasonable expectation of long-term availability
- Preferred platforms: arXiv, GitHub, institutional repositories, established publishers, major conference proceedings

---

## Exclusion Criteria

A resource is **excluded** if any of the following apply:

### Content Exclusions
- **Promotional material** — Content whose primary purpose is marketing a product, service, or company
- **Low-effort content** — Shallow blog posts, listicles, or aggregation pages that add no original insight
- **Outdated content** — Resources that have been superseded by significantly better alternatives and contain no historical value
- **Paywalled without alternatives** — Content locked behind a paywall with no free version available
- **Non-English content** — Resources without an English version or translation
- **Offensive or harmful content** — Content that promotes harm, discrimination, or unethical AI applications

### Technical Exclusions
- **Broken URLs** — Resources with URLs that return 4xx or 5xx errors at the time of review
- **Duplicates** — Resources that substantially overlap with an existing entry (same content, different URL)
- **Previously rejected** — Resources listed in `data/rejected.json` unless the rejection reason has been addressed
- **Auto-generated spam** — Content that appears to be machine-generated without meaningful human curation or review

### Scope Exclusions
- **Pure software engineering** — Programming tutorials or tools with no specific AI/ML relevance
- **News articles** — Journalistic coverage of AI without technical depth (press releases, news summaries)
- **Job postings** — Employment listings or career advice
- **Social media posts** — Individual tweets, LinkedIn posts, or forum comments (threads linking to substantial content are acceptable if the linked content qualifies)

---

## Scoring Rubric

Resources are scored on a scale of **0 to 10** across five dimensions. The final quality score is the weighted average:

### Dimensions

| Dimension | Weight | Description |
|-----------|--------|-------------|
| **Relevance** | 25% | How directly the resource relates to AI/ML research and practice |
| **Recency** | 15% | How current the content is; foundational works receive a recency bonus |
| **Authority** | 20% | Credibility of the authors, institution, or publication venue |
| **Uniqueness** | 15% | Whether the resource offers perspectives or information not easily found elsewhere |
| **Technical Depth** | 25% | Level of technical rigor, detail, and insight provided |

### Scoring Scale

| Score | Label | Description |
|-------|-------|-------------|
| 9.0–10.0 | **Exceptional** | Landmark contribution; foundational paper, definitive tool, or gold-standard dataset |
| 7.5–8.9 | **High Quality** | Significant contribution with strong technical merit and broad applicability |
| 6.0–7.4 | **Good** | Solid resource that provides clear value to the AI research community |
| 4.0–5.9 | **Below Threshold** | Has some merit but does not meet the minimum bar for inclusion |
| 0.0–3.9 | **Excluded** | Lacks relevance, quality, or originality for this collection |

### Scoring Examples

**Score 9.5 — Exceptional:**
> "Attention Is All You Need" (Vaswani et al., 2017) — Foundational paper introducing the Transformer architecture. Maximum relevance, maximum authority (Google Brain, 100k+ citations), strong uniqueness as the original source, and exceptional technical depth.

**Score 7.8 — High Quality:**
> A well-maintained PyTorch library for efficient fine-tuning of large language models with comprehensive documentation, active maintenance, 5k+ GitHub stars, and novel implementation approaches.

**Score 6.2 — Good:**
> A tutorial blog post from a university researcher explaining diffusion model sampling methods with clear code examples. Good technical depth and relevance but limited novelty.

**Score 4.5 — Below Threshold:**
> A brief blog post summarizing a well-known technique without adding original insight. Moderate relevance but insufficient depth and uniqueness.

---

## Review Process

### Automated Review (AI Agent)

1. The agent evaluates each candidate against the scoring rubric using the Anthropic Claude API
2. Resources scoring below 6.0 are automatically filtered out
3. Deduplication checks run against `data/resources.json` and `data/rejected.json`
4. Passing resources are submitted as a pull request for human review

### Human Review

1. A maintainer reviews the pull request using the [PR checklist](.github/PULL_REQUEST_TEMPLATE.md)
2. Each resource is verified against the inclusion criteria:
   - URL loads successfully
   - Title and type are accurate
   - Tags follow conventions
   - Content is valuable and unbiased
   - No duplicate exists
3. **To approve:** Approve the PR via GitHub's review interface
4. **To reject a resource:** Comment with `REJECT: <url> | <reason>`
5. On merge, approved resources are integrated into `data/resources.json`

### Rejection Handling

- Rejected resources are moved to `data/rejected.json` with the rejection reason and timestamp
- The agent checks `data/rejected.json` during future crawls to avoid re-proposing rejected resources
- A rejected resource can be reconsidered if the rejection reason is addressed (e.g., a broken URL is fixed)

### Appeals

If you believe a resource was incorrectly rejected:

1. Open an issue referencing the original rejection
2. Explain why the rejection reason no longer applies
3. A maintainer will re-evaluate the resource

---

## Maintenance Schedule

### Regular Maintenance

| Task | Frequency | Description |
|------|-----------|-------------|
| **AI Crawl** | Mon + Thu (08:00 UTC) | Automated discovery of new resources |
| **PR Review** | Within 48 hours | Human review of agent-submitted PRs |
| **Link Checking** | Monthly | Verify all resource URLs are still accessible |
| **Stale Resource Audit** | Quarterly | Review resources older than 2 years for continued relevance |
| **Tag Cleanup** | Quarterly | Consolidate redundant tags and update conventions |
| **Rejected List Pruning** | Biannually | Remove rejected entries older than 1 year to allow re-evaluation |

### Incident Response

- **Broken links:** If a resource URL breaks, a maintainer will attempt to find an updated URL. If no replacement exists, the resource is moved to a `deprecated` status with a note.
- **Incorrect content:** If a resource is found to contain inaccurate or misleading information, it is flagged for review and may be removed or annotated.
- **Copyright concerns:** If a resource is flagged for copyright issues, it is immediately removed pending resolution.

---

## Version History

| Date | Change |
|------|--------|
| 2025-06-01 | Initial content policy established |
