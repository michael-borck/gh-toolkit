"""Unit tests for the tag vocabulary loader."""

import pytest

from gh_toolkit.core.tag_vocabulary import load_vocabulary


class TestTagVocabulary:
    def test_loads_valid_vocabulary(self, tmp_path):
        path = tmp_path / "tags.yaml"
        path.write_text(
            """
name: Test tags
tags:
  web-app:
    description: Browser apps
    examples:
      - dashboards
    exclusions:
      - CLI tools
  ai:
    description: AI tools
"""
        )

        vocabulary = load_vocabulary(path)

        assert vocabulary.name == "Test tags"
        assert vocabulary.names == ["web-app", "ai"]
        assert vocabulary.tags["web-app"].examples == ["dashboards"]
        assert vocabulary.tags["web-app"].exclusions == ["CLI tools"]

    def test_rejects_invalid_tag_name(self, tmp_path):
        path = tmp_path / "tags.yaml"
        path.write_text(
            """
tags:
  Bad Tag:
    description: nope
"""
        )

        with pytest.raises(ValueError):
            load_vocabulary(path)

    def test_rejects_missing_description(self, tmp_path):
        path = tmp_path / "tags.yaml"
        path.write_text(
            """
tags:
  web-app: {}
"""
        )

        with pytest.raises(ValueError):
            load_vocabulary(path)

    def test_rejects_unknown_key(self, tmp_path):
        path = tmp_path / "tags.yaml"
        path.write_text(
            """
tags:
  web-app:
    description: Browser apps
    colour: blue
"""
        )

        with pytest.raises(ValueError):
            load_vocabulary(path)
