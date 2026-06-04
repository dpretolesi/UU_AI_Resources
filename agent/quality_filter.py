#!/usr/bin/env python3
"""
Quality filter and scoring module for the AI Research Hub crawl agent.

Scores candidate resources on a 0.0-10.0 scale using hard disqualifiers,
positive signals, and negative signals. Optionally calls the Anthropic API
for borderline cases.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLACKLISTED_DOMAINS: set[str] = {
    "medium.com",
    "dev.to",
    "towardsdatascience.com",
    "analyticsvidhya.com",
    "kdnuggets.com",
    "machinelearningmastery.com",
    "datacamp.com",
    "simplilearn.com",
    "geeksforgeeks.org",
    "w3schools.com",
    "tutorialspoint.com",
    "javatpoint.com",
    "guru99.com",
    "edureka.co",
    "intellipaat.com",
}

REPUTABLE_DOMAINS: set[str] = {
    "arxiv.org",
    "openreview.net",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "aclanthology.org",
    "distill.pub",
    "paperswithcode.com",
    "github.com",
    "huggingface.co",
    "ai.google",
    "ai.meta.com",
    "openai.com",
    "deepmind.com",
    "anthropic.com",
    "research.microsoft.com",
    "ai.stanford.edu",
    "cs.stanford.edu",
    "mit.edu",
    "berkeley.edu",
    "cmu.edu",
    "jmlr.org",
    "sciencedirect.com",
    "nature.com",
    "science.org",
    "tensorflow.org",
    "pytorch.org",
    "fast.ai",
    "course.fast.ai",
    "keras.io",
    "scikit-learn.org",
    "commoncrawl.org",
}

VENDOR_MARKETING_KEYWORDS: list[str] = [
    "buy now",
    "limited offer",
    "sign up free trial",
    "exclusive discount",
    "schedule a demo",
    "request a quote",
    "pricing plans",
    "enterprise solution",
    "talk to sales",
    "book a call",
]

SPAM_SEO_PATTERNS: list[re.Pattern] = [
    re.compile(r"top\s+\d+\s+(best|tools|platforms|apps)", re.IGNORECASE),
    re.compile(r"\d+\s+ways\s+to", re.IGNORECASE),
    re.compile(r"ultimate\s+guide\s+to", re.IGNORECASE),
    re.compile(r"everything\s+you\s+need\s+to\s+know", re.IGNORECASE),
    re.compile(r"click\s+here", re.IGNORECASE),
]

OFF_TOPIC_KEYWORDS: list[str] = [
    "cryptocurrency",
    "blockchain mining",
    "forex trading",
    "weight loss",
    "real estate investing",
    "drop shipping",
    "affiliate marketing",
    "multi-level marketing",
    "sports betting",
]

UNDERREPRESENTED_TYPES: set[str] = {
    "dataset",
    "benchmark",
    "podcast",
    "newsletter",
    "community",
    "model",
    "book",
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class QualityRejectionError(Exception):
    """Raised when a resource is hard-disqualified during scoring."""

    def __init__(self, reason: str, url: str = "", domain: str = "") -> None:
        self.reason = reason
        self.url = url
        self.domain = domain
        super().__init__(f"Rejected: {reason} (url={url}, domain={domain})")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScoringBreakdown:
    """Detailed breakdown of how a resource was scored."""

    base_score: float = 5.0
    adjustments: list[tuple[str, float]] = field(default_factory=list)
    final_score: float = 0.0
    disqualified: bool = False
    disqualification_reason: str = ""

    def add(self, reason: str, delta: float) -> None:
        self.adjustments.append((reason, delta))

    def compute(self) -> float:
        total = self.base_score + sum(d for _, d in self.adjustments)
        self.final_score = max(0.0, min(10.0, total))
        return self.final_score


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    """Extract the registrable domain from a URL."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    # Strip www. prefix
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname.lower()


def _check_hard_disqualifiers(
    url: str,
    title: str,
    description: str,
    domain: str,
    access: str | None = None,
    is_link_broken: bool = False,
) -> None:
    """
    Check for hard disqualifiers. Raises QualityRejectionError if any are found.
    """
    # 1. Blacklisted domain
    for blacklisted in BLACKLISTED_DOMAINS:
        if domain == blacklisted or domain.endswith(f".{blacklisted}"):
            raise QualityRejectionError(
                reason=f"Blacklisted domain: {blacklisted}",
                url=url,
                domain=domain,
            )

    # 2. Paywalled (explicit paid access with no academic/open-access value)
    if access == "paid":
        raise QualityRejectionError(
            reason="Resource is paywalled with no open-access alternative",
            url=url,
            domain=domain,
        )

    # 3. Spam / SEO content
    combined_text = f"{title} {description}".lower()
    for pattern in SPAM_SEO_PATTERNS:
        if pattern.search(combined_text):
            raise QualityRejectionError(
                reason=f"Spam/SEO pattern detected: {pattern.pattern}",
                url=url,
                domain=domain,
            )

    # 4. News, not a resource (heuristic: very short description about an event)
    news_indicators = [
        "announced today",
        "breaking:",
        "just released",
        "press release",
        "news roundup",
        "weekly digest",
    ]
    for indicator in news_indicators:
        if indicator in combined_text:
            raise QualityRejectionError(
                reason=f"Appears to be news rather than a resource: '{indicator}'",
                url=url,
                domain=domain,
            )

    # 5. Off-topic
    for keyword in OFF_TOPIC_KEYWORDS:
        if keyword in combined_text:
            raise QualityRejectionError(
                reason=f"Off-topic content detected: '{keyword}'",
                url=url,
                domain=domain,
            )

    # 6. Broken link
    if is_link_broken:
        raise QualityRejectionError(
            reason="Broken link (HTTP error or unreachable)",
            url=url,
            domain=domain,
        )


def _score_positive_signals(
    breakdown: ScoringBreakdown,
    domain: str,
    resource_type: str,
    year: int | None,
    access: str | None,
    authors: list[str] | None,
    description: str,
    title: str,
) -> None:
    """Add positive scoring signals."""
    # Reputable institution / domain
    for reputable in REPUTABLE_DOMAINS:
        if domain == reputable or domain.endswith(f".{reputable}"):
            breakdown.add("Reputable domain/institution", 1.5)
            break

    # Research applicability
    research_keywords = [
        "research",
        "paper",
        "study",
        "experiment",
        "benchmark",
        "evaluation",
        "state-of-the-art",
        "novel",
        "framework",
        "architecture",
        "methodology",
        "ablation",
    ]
    combined = f"{title} {description}".lower()
    research_hits = sum(1 for kw in research_keywords if kw in combined)
    if research_hits >= 2:
        breakdown.add("Research applicability", 1.0)

    # Recency
    if year and year >= 2024:
        breakdown.add("Recent resource (2024+)", 0.5)
    elif year and year >= 2023:
        breakdown.add("Relatively recent resource (2023)", 0.25)

    # Open access
    if access in ("free", "open-access"):
        breakdown.add("Open access", 0.5)

    # Author attribution
    if authors and len(authors) > 0 and any(a.strip() for a in authors):
        breakdown.add("Author attribution present", 0.5)

    # Underrepresented type bonus
    if resource_type in UNDERREPRESENTED_TYPES:
        breakdown.add(f"Underrepresented type: {resource_type}", 1.0)

    # High engagement proxy: description quality (length and detail)
    if len(description) >= 200:
        breakdown.add("Detailed description (engagement proxy)", 1.0)
    elif len(description) >= 100:
        breakdown.add("Moderate description detail", 0.5)


def _score_negative_signals(
    breakdown: ScoringBreakdown,
    description: str,
    title: str,
    resource_type: str,
    known_urls_count: int = 0,
) -> None:
    """Add negative scoring signals."""
    combined = f"{title} {description}".lower()

    # Introductory only
    intro_keywords = [
        "beginner",
        "introduction to",
        "getting started",
        "101",
        "for dummies",
        "what is ai",
        "what is machine learning",
    ]
    intro_hits = sum(1 for kw in intro_keywords if kw in combined)
    if intro_hits >= 2:
        breakdown.add("Introductory-only content", -1.0)
    elif intro_hits == 1:
        breakdown.add("Somewhat introductory", -0.5)

    # Vague description
    if len(description) < 60:
        breakdown.add("Vague/short description", -0.5)

    # Vendor marketing
    marketing_hits = sum(1 for kw in VENDOR_MARKETING_KEYWORDS if kw in combined)
    if marketing_hits >= 2:
        breakdown.add("Vendor marketing language", -1.5)
    elif marketing_hits == 1:
        breakdown.add("Minor marketing language", -0.5)

    # Near-duplicate heuristic (caller should set this based on title similarity)
    # This is a simplified check — the crawl agent performs more thorough dedup
    if known_urls_count > 0:
        breakdown.add("Potential near-duplicate", -1.0)


# ---------------------------------------------------------------------------
# LLM scoring for borderline cases
# ---------------------------------------------------------------------------


def _llm_score_borderline(
    title: str,
    url: str,
    description: str,
    resource_type: str,
    current_score: float,
) -> Optional[float]:
    """
    Call the Anthropic API for borderline cases (score between 5.0 and 7.0).
    Returns an adjusted score or None if the API is unavailable.
    """
    # api_key = os.environ.get("ANTHROPIC_API_KEY")
    if False:
        logger.debug("ANTHROPIC_API_KEY not set; skipping LLM scoring.")
        return None

    try:
        import ollama

        prompt = (
            f"You are evaluating an AI/ML resource for inclusion in a curated research hub.\n\n"
            f"Title: {title}\n"
            f"URL: {url}\n"
            f"Type: {resource_type}\n"
            f"Description: {description}\n"
            f"Current heuristic score: {current_score}/10\n\n"
            f"Rate this resource from 0-10 based on:\n"
            f"- Educational or research value for AI/ML practitioners\n"
            f"- Uniqueness and quality of content\n"
            f"- Trustworthiness of the source\n"
            f"- Practical applicability\n\n"
            f"Respond with ONLY a single number between 0.0 and 10.0, nothing else."
        )

        response = ollama.chat(
            model="gemma4:e4b-mlx",
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response['message']['content'].strip()
        llm_score = float(response_text)
        llm_score = max(0.0, min(10.0, llm_score))
        logger.info(
            f"LLM scored '{title}' at {llm_score} (heuristic was {current_score})"
        )
        # Average the heuristic and LLM scores
        return round((current_score + llm_score) / 2, 2)

    except ImportError:
        logger.warning("ollama package not installed; skipping LLM scoring.")
        return None
    except (ValueError, IndexError, AttributeError) as e:
        logger.warning(f"Failed to parse LLM score: {e}")
        return None
    except Exception as e:
        logger.warning(f"LLM scoring failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_resource(
    url: str,
    title: str,
    description: str,
    resource_type: str,
    year: int | None = None,
    access: str | None = None,
    authors: list[str] | None = None,
    is_link_broken: bool = False,
    near_duplicate_count: int = 0,
    use_llm_fallback: bool = True,
) -> tuple[float, ScoringBreakdown]:
    """
    Score a candidate resource on a 0.0 to 10.0 scale.

    Args:
        url: The resource URL.
        title: The resource title.
        description: The resource description.
        resource_type: One of the valid resource type enum values.
        year: Publication/release year (optional).
        access: Access model (optional).
        authors: List of author names (optional).
        is_link_broken: Whether the URL returned an error.
        near_duplicate_count: Number of near-duplicates found.
        use_llm_fallback: Whether to use LLM scoring for borderline cases.

    Returns:
        Tuple of (final_score, ScoringBreakdown).

    Raises:
        QualityRejectionError: If the resource is hard-disqualified.
    """
    domain = _extract_domain(url)
    breakdown = ScoringBreakdown()

    # --- Hard disqualifiers (raise on failure) ---
    _check_hard_disqualifiers(
        url=url,
        title=title,
        description=description,
        domain=domain,
        access=access,
        is_link_broken=is_link_broken,
    )

    # --- Positive signals ---
    _score_positive_signals(
        breakdown=breakdown,
        domain=domain,
        resource_type=resource_type,
        year=year,
        access=access,
        authors=authors,
        description=description,
        title=title,
    )

    # --- Negative signals ---
    _score_negative_signals(
        breakdown=breakdown,
        description=description,
        title=title,
        resource_type=resource_type,
        known_urls_count=near_duplicate_count,
    )

    score = breakdown.compute()

    # --- LLM fallback for borderline cases ---
    if use_llm_fallback and 5.0 <= score <= 7.0:
        llm_score = _llm_score_borderline(
            title=title,
            url=url,
            description=description,
            resource_type=resource_type,
            current_score=score,
        )
        if llm_score is not None:
            breakdown.add(f"LLM adjustment ({score} -> {llm_score})", llm_score - score)
            score = breakdown.compute()

    logger.info(
        f"Scored '{title}': {score}/10 "
        f"({len(breakdown.adjustments)} adjustments)"
    )
    return score, breakdown


def is_acceptable(score: float, threshold: float = 6.0) -> bool:
    """Check if a score meets the acceptance threshold."""
    return score >= threshold


if __name__ == "__main__":
    # Quick self-test
    logging.basicConfig(level=logging.INFO)

    score_val, bd = score_resource(
        url="https://arxiv.org/abs/2301.00001",
        title="A Novel Transformer Architecture for Efficient Inference",
        description=(
            "We propose a new transformer architecture that reduces inference "
            "time by 40% while maintaining accuracy on standard NLP benchmarks. "
            "Our approach uses sparse attention patterns and dynamic routing to "
            "achieve state-of-the-art efficiency on multiple tasks."
        ),
        resource_type="paper",
        year=2024,
        access="open-access",
        authors=["Alice Researcher", "Bob Scientist"],
        use_llm_fallback=False,
    )
    print(f"Score: {score_val}/10")
    print(f"Adjustments:")
    for reason, delta in bd.adjustments:
        print(f"  {'+' if delta >= 0 else ''}{delta:.1f}  {reason}")
    assert score_val >= 6.0, f"Expected score >= 6.0, got {score_val}"

    # Test hard disqualifier
    try:
        score_resource(
            url="https://medium.com/some-article",
            title="Test Article",
            description="A test article on a blacklisted domain for validation purposes.",
            resource_type="blog",
            use_llm_fallback=False,
        )
        assert False, "Should have raised QualityRejectionError"
    except QualityRejectionError:
        print("Blacklisted domain correctly rejected.")

    print("All quality_filter self-tests passed.")
