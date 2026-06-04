## Description

<!-- Briefly describe the resources being added or changed. -->

## Submission Type

- [ ] 🤖 Agent — Automated submission by AI crawl agent
- [ ] 👤 Human — Manual submission by a contributor

## Resources

<!-- List the resources included in this PR. -->

| Title | URL | Type |
|-------|-----|------|
|       |     |      |

## Review Checklist

Before approving, verify each resource meets the following criteria:

- [ ] **URL is live** — The resource URL loads successfully and is not behind a paywall
- [ ] **Title is accurate** — The title faithfully represents the content
- [ ] **Type is correct** — The resource type (paper, tool, dataset, etc.) is appropriate
- [ ] **Tags are valid** — Tags follow the project's [tag conventions](CONTRIBUTING.md#tag-conventions) and are relevant
- [ ] **Useful for researchers** — The resource provides genuine value to the AI research community
- [ ] **No commercial bias** — The resource is not primarily promotional or marketing material
- [ ] **Not a duplicate** — The resource does not already exist in `data/resources.json`
- [ ] **Quality score ≥ 6.0** — The resource meets the minimum quality threshold

## Rejecting a Resource

To reject a specific resource from this PR, leave a comment with the following format:

```
REJECT: <url> | <reason>
```

**Example:**
```
REJECT: https://example.com/paper | Duplicate of existing entry; already indexed under a different URL
```

The rejection handler will automatically move the resource to `data/rejected.json` and remove it from the PR.

## Approving

Once all resources pass the review checklist, approve and merge the PR. The `process-pending` workflow will automatically integrate the resources into `data/resources.json`.
