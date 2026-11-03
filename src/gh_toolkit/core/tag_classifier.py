"""Classify repositories against a standard tag vocabulary.

The classifier asks one model for a probability per standard tag plus a small
number of free tags. The model is an implementation detail: the proposal and
validation logic is deterministic, so a System One or TypeSafe classifier can
replace the Anthropic call without changing the command.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, cast

from rich.console import Console

from gh_toolkit.core.llm import DEFAULT_LLM_MODEL
from gh_toolkit.core.tag_vocabulary import TagVocabulary

console = Console()

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_GENERIC_FREE_TAGS = {
    "app",
    "apps",
    "code",
    "development",
    "github",
    "misc",
    "other",
    "programming",
    "project",
    "projects",
    "repo",
    "repository",
    "software",
    "tech",
    "technology",
    "tool",
    "tools",
}


@dataclass
class TagProposal:
    """A validated tag proposal for one repository."""

    standard: dict[str, float]
    selected: list[str]
    review: dict[str, float]
    free: list[str]
    final: list[str]
    reason: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard_scores": self.standard,
            "selected_standard": self.selected,
            "review_standard": self.review,
            "free_tags": self.free,
            "final_topics": self.final,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass
class TagClassifier:
    """Ask a model to score a repository against a tag vocabulary."""

    vocabulary: TagVocabulary
    anthropic_api_key: str | None = None
    model: str = DEFAULT_LLM_MODEL
    free_tag_limit: int = 2
    min_probability: float = 0.8
    review_probability: float = 0.3
    _client: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.anthropic_api_key:
            return
        try:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self.anthropic_api_key)
        except ImportError:
            console.print(
                "[yellow]Anthropic package not available; using rule-based tagging[/yellow]"
            )
            self._client = None

    def classify(
        self,
        repo_data: dict[str, Any],
        readme: str = "",
        existing_topics: list[str] | None = None,
    ) -> TagProposal:
        existing = list(existing_topics or [])
        if self._client is None:
            return self._fallback(repo_data, existing)

        try:
            raw = self._ask_model(repo_data, readme, existing)
        except Exception as e:
            console.print(f"[yellow]LLM tag classification failed: {e}[/yellow]")
            return self._fallback(repo_data, existing)

        if raw is None:
            return self._fallback(repo_data, existing)

        return self._validate(raw, repo_data, existing)

    def _ask_model(
        self,
        repo_data: dict[str, Any],
        readme: str,
        existing: list[str],
    ) -> dict[str, Any] | None:
        vocabulary_text = "\n".join(
            f"- {tag.name}: {tag.description}"
            + (f" Examples: {', '.join(tag.examples)}" if tag.examples else "")
            + (f" Not: {', '.join(tag.exclusions)}" if tag.exclusions else "")
            for tag in self.vocabulary.tags.values()
        )

        prompt = f"""Tag this GitHub repository for discovery.

Standard tags:
{vocabulary_text}

Return JSON only, with this shape:
{{
  "standard": {{"tag-name": 0.0}},
  "free": ["one-or-two-specific-tags"],
  "reason": "short explanation"
}}

Rules:
- Score every standard tag from 0 to 1. A repository may match several tags.
- Use 1.0 for a clear match, 0.0 for a clear miss, and a middle value when unsure.
- Add at most {self.free_tag_limit} free tags. They must be lowercase,
  hyphenated, specific to this repository, and not in the standard set.
- Do not use generic tags such as code, project, tools, software, app, or github.
- Reuse relevant existing topics as free tags when they still fit.
- Keep the reason to one sentence.

Repository:
Name: {repo_data.get("name", "")}
Full name: {repo_data.get("full_name", "")}
Description: {repo_data.get("description", "")}
Language: {repo_data.get("language", "")}
Existing topics: {", ".join(existing) if existing else "none"}

README excerpt:
{readme[:2500] if readme else "No README available"}
"""

        response = self._client.messages.create(
            model=self.model,
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0] if response.content else None
        text = getattr(content, "text", "").strip()
        if not text:
            return None

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        parsed = json.loads(text[start : end + 1])
        return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else None

    def _validate(
        self,
        raw: dict[str, Any],
        repo_data: dict[str, Any],
        existing: list[str],
    ) -> TagProposal:
        raw_scores = raw.get("standard")
        scores: dict[str, float] = {}
        if isinstance(raw_scores, dict):
            scores_raw = cast(dict[str, Any], raw_scores)
            for name in self.vocabulary.names:
                value = scores_raw.get(name, 0.0)
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    score = 0.0
                scores[name] = min(1.0, max(0.0, score))
        else:
            scores = dict.fromkeys(self.vocabulary.names, 0.0)

        selected = [
            name for name, score in scores.items() if score >= self.min_probability
        ]
        review = {
            name: score
            for name, score in scores.items()
            if self.review_probability <= score < self.min_probability
        }
        if not selected and review:
            best = max(review, key=lambda name: review[name])
            selected = [best]
            review.pop(best)

        raw_free = raw.get("free")
        free_candidates = (
            [str(item) for item in cast(list[object], raw_free)]
            if isinstance(raw_free, list)
            else []
        )
        free = self._clean_free_tags(free_candidates, selected, existing)
        final = self._merge_topics(selected, free, existing)
        reason = str(raw.get("reason") or "").strip()

        return TagProposal(
            standard=scores,
            selected=selected,
            review=review,
            free=free,
            final=final,
            reason=reason,
            source="llm",
        )

    def _fallback(self, repo_data: dict[str, Any], existing: list[str]) -> TagProposal:
        text = " ".join(
            [
                str(repo_data.get("name") or ""),
                str(repo_data.get("description") or ""),
                " ".join(existing),
            ]
        ).lower()

        keyword_map = {
            "web-app": ["web", "site", "website", "dashboard", "spa", "html"],
            "ai": ["ai", "llm", "machine learning", "anthropic", "openai", "gpt"],
            "education": ["teach", "course", "lesson", "student", "education", "lab"],
            "cli": ["cli", "command line", "terminal", "shell"],
            "research": ["research", "paper", "experiment", "benchmark", "study"],
            "book": ["book", "quarto", "chapter", "manuscript"],
            "desktop-app": ["desktop", "electron", "tauri", "gui"],
            "cybersecurity": ["security", "cyber", "hacking", "penetration", "defence"],
            "operations": [
                "operations",
                "workspace",
                "hq",
                "index",
                "admin",
                "internal",
            ],
        }

        scores: dict[str, float] = {}
        for name in self.vocabulary.names:
            keywords = keyword_map.get(name, [])
            scores[name] = 1.0 if any(k in text for k in keywords) else 0.0

        selected = [
            name for name, score in scores.items() if score >= self.min_probability
        ]
        review = {
            name: score
            for name, score in scores.items()
            if self.review_probability <= score < self.min_probability
        }
        if not selected and review:
            best = max(review, key=lambda name: review[name])
            selected = [best]
            review.pop(best)
        free = self._clean_free_tags(existing, selected, existing)
        final = self._merge_topics(selected, free, existing)

        return TagProposal(
            standard=scores,
            selected=selected,
            review=review,
            free=free,
            final=final,
            reason="Rule-based fallback",
            source="fallback",
        )

    def _clean_free_tags(
        self,
        candidates: list[str],
        selected: list[str],
        existing: list[str],
    ) -> list[str]:
        standard = set(self.vocabulary.names)
        result: list[str] = []
        for candidate in candidates:
            tag = re.sub(r"[^a-z0-9]+", "-", candidate.lower()).strip("-")
            if not tag or len(tag) > 50 or not _TAG_RE.fullmatch(tag):
                continue
            if tag in standard or tag in _GENERIC_FREE_TAGS:
                continue
            if tag in result:
                continue
            result.append(tag)
            if len(result) >= self.free_tag_limit:
                break
        return result

    def _merge_topics(
        self,
        selected: list[str],
        free: list[str],
        existing: list[str],
    ) -> list[str]:
        standard = set(self.vocabulary.names)
        merged: list[str] = []
        for tag in [*selected, *free, *existing]:
            if tag in standard and tag not in selected:
                continue
            if tag in _GENERIC_FREE_TAGS:
                continue
            if tag not in merged:
                merged.append(tag)
        return merged[:20]
