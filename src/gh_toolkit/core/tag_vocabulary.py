"""Load and validate the standard tag vocabulary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TOP_LEVEL_KEYS = {"name", "version", "tags"}
_TAG_KEYS = {"description", "examples", "exclusions"}


@dataclass(frozen=True)
class TagDefinition:
    """One standard tag and the guidance the classifier sees."""

    name: str
    description: str
    examples: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TagVocabulary:
    """A named set of standard tags."""

    name: str
    tags: dict[str, TagDefinition]

    @property
    def names(self) -> list[str]:
        return list(self.tags)


def load_vocabulary(path: str | Path) -> TagVocabulary:
    """Load a YAML vocabulary, raising ValueError on malformed content."""
    vocab_path = Path(path)
    if not vocab_path.is_file():
        raise FileNotFoundError(f"Tag vocabulary not found: {vocab_path}")

    try:
        with open(vocab_path, encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {vocab_path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Tag vocabulary {vocab_path} must be a mapping")

    data = cast(dict[str, Any], data)
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(
            f"Unknown vocabulary keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(_TOP_LEVEL_KEYS))}"
        )

    raw_tags = data.get("tags")
    if not isinstance(raw_tags, dict) or not raw_tags:
        raise ValueError("Tag vocabulary needs a non-empty 'tags' mapping")

    tags: dict[str, TagDefinition] = {}
    for name, raw_definition in cast(dict[str, Any], raw_tags).items():
        if not _TAG_RE.fullmatch(name):
            raise ValueError(
                f"Invalid tag name {name!r}: use lowercase letters, numbers, "
                "and hyphens"
            )
        if len(name) > 50:
            raise ValueError(f"Tag name too long: {name}")

        if not isinstance(raw_definition, dict):
            raise ValueError(f"Tag {name!r} must be a mapping")
        definition = cast(dict[str, Any], raw_definition)
        unknown_tag_keys = set(definition) - _TAG_KEYS
        if unknown_tag_keys:
            raise ValueError(
                f"Unknown keys for tag {name!r}: {', '.join(sorted(unknown_tag_keys))}"
            )

        description = str(definition.get("description") or "").strip()
        if not description:
            raise ValueError(f"Tag {name!r} needs a description")

        tags[name] = TagDefinition(
            name=name,
            description=description,
            examples=_string_list(definition.get("examples"), name, "examples"),
            exclusions=_string_list(definition.get("exclusions"), name, "exclusions"),
        )

    return TagVocabulary(
        name=str(data.get("name") or "Tag vocabulary"),
        tags=tags,
    )


def _string_list(raw: Any, tag: str, field_name: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} for tag {tag!r} must be a list")
    return [str(item) for item in cast(list[Any], raw)]
