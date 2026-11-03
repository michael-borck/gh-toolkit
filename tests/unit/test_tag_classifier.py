"""Unit tests for the tag classifier."""

import json
from unittest.mock import Mock

from gh_toolkit.core.tag_classifier import TagClassifier
from gh_toolkit.core.tag_vocabulary import TagDefinition, TagVocabulary

VOCABULARY = TagVocabulary(
    name="Test",
    tags={
        "web-app": TagDefinition("web-app", "Browser apps"),
        "ai": TagDefinition("ai", "AI tools"),
        "education": TagDefinition("education", "Teaching tools"),
        "cli": TagDefinition("cli", "CLI tools"),
        "research": TagDefinition("research", "Research"),
        "book": TagDefinition("book", "Books"),
        "desktop-app": TagDefinition("desktop-app", "Desktop apps"),
        "cybersecurity": TagDefinition("cybersecurity", "Security"),
    },
)


class TestTagClassifier:
    def test_fallback_uses_keywords(self):
        classifier = TagClassifier(vocabulary=VOCABULARY)

        proposal = classifier.classify(
            {
                "name": "security-web-lab",
                "description": "A web app for teaching AI security",
            }
        )

        assert "web-app" in proposal.selected
        assert "ai" in proposal.selected
        assert "education" in proposal.selected
        assert "cybersecurity" in proposal.selected
        assert proposal.source == "fallback"

    def test_llm_scores_are_validated_and_filtered(self):
        client = Mock()
        client.messages.create.return_value.content = [
            Mock(
                text=json.dumps(
                    {
                        "standard": {
                            "web-app": 0.92,
                            "ai": 0.85,
                            "education": 0.4,
                            "cli": 0.1,
                        },
                        "free": ["code", "python", "classroom"],
                        "reason": "web AI teaching tool",
                    }
                )
            )
        ]
        classifier = TagClassifier(vocabulary=VOCABULARY, anthropic_api_key="key")
        classifier._client = client

        proposal = classifier.classify(
            {"name": "repo", "description": "A web AI teaching tool"},
            existing_topics=["python"],
        )

        assert proposal.selected == ["web-app", "ai"]
        assert proposal.review == {"education": 0.4}
        assert proposal.free == ["python", "classroom"]
        assert proposal.final == ["web-app", "ai", "python", "classroom"]
        assert proposal.source == "llm"

    def test_free_tags_respect_limit_and_generic_blocklist(self):
        classifier = TagClassifier(vocabulary=VOCABULARY, free_tag_limit=1)

        proposal = classifier.classify(
            {
                "name": "repo",
                "description": "A web app",
                "topics": [],
            },
            existing_topics=["code", "python", "classroom"],
        )

        assert proposal.free == ["python"]
