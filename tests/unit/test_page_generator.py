"""Unit tests for PageGenerator class."""

from gh_toolkit.core.page_generator import PageGenerator


class TestPageGenerator:
    """Test PageGenerator functionality."""

    def test_init(self):
        """Test PageGenerator initialization."""
        markdown = "# Test Project\n\nA test project description."
        generator = PageGenerator(markdown)

        assert generator.markdown_text == markdown
        assert generator.title == "Project Landing Page"
        assert generator.description == ""
        assert generator.sections == []
        assert generator.links == {}

    def test_extract_title_and_description(self):
        """Test title and description extraction."""
        markdown = """# My Awesome Project

This is a really cool project that does amazing things.

## Features

- Feature 1
- Feature 2
"""
        generator = PageGenerator(markdown)
        generator._extract_title_and_description()

        assert generator.title == "My Awesome Project"
        assert (
            generator.description
            == "This is a really cool project that does amazing things."
        )

    def test_extract_title_only(self):
        """Test extraction when only title is present."""
        markdown = """# Simple Project

## Features

- Feature 1
"""
        generator = PageGenerator(markdown)
        generator._extract_title_and_description()

        assert generator.title == "Simple Project"
        assert generator.description == ""

    def test_extract_links_github(self):
        """Test GitHub link extraction."""
        markdown = """# Project

Check out the code at [GitHub](https://github.com/user/project).

## Features

Great features here.
"""
        generator = PageGenerator(markdown)
        generator._extract_links()

        assert "repo" in generator.links
        assert generator.links["repo"]["url"] == "https://github.com/user/project"
        assert generator.links["repo"]["label"] == "GitHub"

    def test_extract_links_template(self):
        """Test template link extraction."""
        markdown = """# Template Project

[Use this template](https://github.com/user/template/generate)

## Usage

How to use this template.
"""
        generator = PageGenerator(markdown)
        generator._extract_links()

        assert "template" in generator.links
        assert (
            generator.links["template"]["url"]
            == "https://github.com/user/template/generate"
        )
        assert generator.links["template"]["label"] == "Use this template"

    def test_parse_markdown_basic(self):
        """Test basic markdown parsing."""
        markdown = """# Test Project

This is the hero section content.

## Installation

Install instructions here.

## Usage

Usage instructions here.
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()

        # Should have hero + 2 sections
        assert len(generator.sections) == 3

        # Check hero section
        hero = generator.sections[0]
        assert hero["type"] == "hero"
        assert hero["title"] == "Test Project"
        assert "This is the hero section content" in hero["content"]

        # Check other sections
        assert generator.sections[1]["title"] == "Installation"
        assert generator.sections[2]["title"] == "Usage"

    def test_parse_markdown_with_badges(self):
        """Test parsing markdown with badges (should be removed)."""
        markdown = """# Project with Badges

![Build Status](https://img.shields.io/badge/build-passing-green)

This project has badges that should be removed.

## Features

- Feature 1
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()

        hero = generator.sections[0]
        # Badge should be removed from content
        assert "img.shields.io" not in hero["content"]
        assert "This project has badges" in hero["content"]

    def test_slugify(self):
        """Test text slugification."""
        generator = PageGenerator("# Test")

        assert generator._slugify("Installation Guide") == "installation-guide"
        assert generator._slugify("API/SDK") == "api-sdk"
        assert generator._slugify("Getting Started") == "getting-started"
        assert generator._slugify("C++ Code") == "c++-code"

    def test_render_html_basic(self):
        """Test HTML rendering."""
        markdown = """# Test Project

A simple test project.

## Features

- Great feature
- Another feature
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()
        html_output = generator.render_html()

        assert "<!DOCTYPE html>" in html_output
        assert "Test Project" in html_output
        assert "Features" in html_output
        assert "Great feature" in html_output
        assert "Tailwind" in html_output or "tailwindcss" in html_output

    def test_render_jekyll_basic(self):
        """Test Jekyll rendering."""
        markdown = """# Test Project

A simple test project for Jekyll.

## Features

- Jekyll feature
- Another feature
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()
        jekyll_output = generator.render_jekyll()

        assert "---" in jekyll_output
        assert "layout: default" in jekyll_output
        assert "title: Test Project" in jekyll_output
        assert "description: A simple test project for Jekyll." in jekyll_output
        assert "Jekyll feature" in jekyll_output

    def test_render_jekyll_no_description(self):
        """Test Jekyll rendering without description."""
        markdown = """# Simple Project

## Features

- Feature only
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()
        jekyll_output = generator.render_jekyll()

        assert "---" in jekyll_output
        assert "layout: default" in jekyll_output
        assert "title: Simple Project" in jekyll_output
        # Should not have description field when empty
        assert "description:" not in jekyll_output

    def test_render_jekyll_override_title_description(self):
        """Test Jekyll rendering with overridden title and description."""
        markdown = """# Original Title

Original description.

## Features

- Feature 1
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()

        # Override title and description
        generator.title = "Custom Title"
        generator.description = "Custom description"

        jekyll_output = generator.render_jekyll()

        assert "title: Custom Title" in jekyll_output
        assert "description: Custom description" in jekyll_output

    def test_feature_section_rendering(self):
        """Test special rendering for feature sections."""
        markdown = """# Project

Description here.

## Features

- **Feature One**: Description of feature one
- **Feature Two**: Description of feature two
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()
        html_output = generator.render_html()

        # Should have grid layout for features
        assert "grid gap-8 md:grid-cols-2 lg:grid-cols-3" in html_output
        assert "Feature One" in html_output
        assert "Feature Two" in html_output

    def test_links_in_hero_buttons(self):
        """Test that links appear as buttons in hero section."""
        markdown = """# Project with Links

[View on GitHub](https://github.com/user/project)
[Use this template](https://github.com/user/project/generate)

A project with various links.

## Features

- Feature 1
"""
        generator = PageGenerator(markdown)
        generator.parse_markdown()
        html_output = generator.render_html()

        # Should have GitHub and template buttons
        assert "View on GitHub" in html_output
        assert "Use this template" in html_output
        assert "bg-green-600" in html_output  # Template button color
        assert "Get Started" in html_output  # Default button

    def test_slugify_blocks_attribute_injection(self):
        """Slugs are interpolated into id/href and must not break out."""
        generator = PageGenerator("# Test")
        slug = generator._slugify('bad " onmouseover="alert(1) <img src=x>')

        assert '"' not in slug
        assert "<" not in slug
        assert ">" not in slug
