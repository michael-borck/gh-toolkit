"""Unit tests for American to Australian spelling checks."""

from gh_toolkit.core.spelling import (
    apply_australian_spelling,
    find_american_spellings,
    suggest_australian,
    truncate_at_word,
)


class TestSpelling:
    def test_finds_common_spellings(self):
        issues = find_american_spellings(
            "An organization for color analysis and behavior."
        )

        assert [(issue.word, issue.suggestion) for issue in issues] == [
            ("organization", "organisation"),
            ("color", "colour"),
            ("behavior", "behaviour"),
        ]

    def test_preserves_case(self):
        issues = find_american_spellings("Organized and ANALYZE this.")

        assert [(issue.word, issue.suggestion) for issue in issues] == [
            ("Organized", "Organised"),
            ("ANALYZE", "ANALYSE"),
        ]

    def test_skips_urls_emails_and_inline_code(self):
        text = "https://example.com/organization color `color` me@example.com"

        issues = find_american_spellings(text)

        assert [issue.word for issue in issues] == ["color"]

    def test_does_not_flag_australian_or_context_words(self):
        text = "organisation colour license catalog dialog artifact program"

        assert find_american_spellings(text) == []

    def test_empty_input(self):
        assert find_american_spellings(None) == []
        assert find_american_spellings("") == []

    def test_suggest_australian_preserves_case(self):
        assert suggest_australian("color") == "colour"
        assert suggest_australian("Color") == "Colour"
        assert suggest_australian("COLOR") == "COLOUR"


class TestApplySpelling:
    def test_replaces_prose_and_preserves_case(self):
        text = "An organization tool. Organized for color analysis."

        result = apply_australian_spelling(text)

        assert result == "An organisation tool. Organised for colour analysis."

    def test_preserves_urls_emails_and_code(self):
        text = "See https://example.com/organization `color` and color."

        result = apply_australian_spelling(text)

        assert "https://example.com/organization" in result
        assert "`color`" in result
        assert "colour." in result

    def test_empty_input(self):
        assert apply_australian_spelling("") == ""


class TestTruncateAtWord:
    def test_short_text_is_unchanged(self):
        assert truncate_at_word("short text", 20) == "short text"

    def test_cuts_at_word_boundary(self):
        assert truncate_at_word("one two three four", 12) == "one two"

    def test_never_returns_empty(self):
        assert truncate_at_word("supercalifragilistic", 5) == "super"
