"""Unit tests for SiteGenerator."""

import pytest

from gh_toolkit.core.site_generator import SiteGenerator


class TestSiteGenerator:
    """Test SiteGenerator functionality."""

    def test_init(self):
        """Test SiteGenerator initialization."""
        generator = SiteGenerator()

        assert "educational" in generator.themes
        assert "resume" in generator.themes
        assert "research" in generator.themes
        assert "portfolio" in generator.themes

        # Check theme structure
        for _theme_name, theme_config in generator.themes.items():
            assert "title" in theme_config
            assert "description" in theme_config
            assert "accent_color" in theme_config
            assert "category_order" in theme_config

    def test_generate_site_basic(self, tmp_path, sample_extracted_repos):
        """Test basic site generation."""
        generator = SiteGenerator()
        output_file = tmp_path / "test_site.html"

        generator.generate_site(
            repos_data=sample_extracted_repos,
            theme="educational",
            output_file=str(output_file),
        )

        assert output_file.exists()
        content = output_file.read_text()

        # Check basic HTML structure
        assert "<!DOCTYPE html>" in content
        assert '<html lang="en">' in content
        assert "Educational Tools Collection" in content
        assert "web-app" in content
        assert "data-tool" in content

    def test_generate_site_with_custom_title(self, tmp_path, sample_extracted_repos):
        """Test site generation with custom title and description."""
        generator = SiteGenerator()
        output_file = tmp_path / "custom_site.html"

        custom_title = "My Custom Portfolio"
        custom_description = "My awesome projects"

        generator.generate_site(
            repos_data=sample_extracted_repos,
            theme="portfolio",
            output_file=str(output_file),
            title=custom_title,
            description=custom_description,
        )

        content = output_file.read_text()
        assert custom_title in content
        assert custom_description in content

    def test_generate_site_with_metadata(
        self, tmp_path, sample_extracted_repos, sample_site_metadata
    ):
        """Test site generation with metadata."""
        generator = SiteGenerator()
        output_file = tmp_path / "metadata_site.html"

        generator.generate_site(
            repos_data=sample_extracted_repos,
            theme="resume",
            output_file=str(output_file),
            metadata=sample_site_metadata,
        )

        content = output_file.read_text()

        # Check metadata features are included
        assert "🌐" in content  # web-app icon
        assert "📊" in content  # data-tool icon
        assert "Responsive design" in content
        assert "Pandas integration" in content

    def test_invalid_theme(self, sample_extracted_repos):
        """Test error handling for invalid theme."""
        generator = SiteGenerator()

        with pytest.raises(ValueError) as exc_info:
            generator.generate_site(
                repos_data=sample_extracted_repos, theme="nonexistent-theme"
            )

        assert "Unknown theme: nonexistent-theme" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_group_by_category(self, sample_extracted_repos):
        """Test repository grouping by category."""
        generator = SiteGenerator()
        theme_config = generator.themes["educational"]

        categories = generator._group_by_category(sample_extracted_repos, theme_config)

        # Should have 2 categories
        assert len(categories) == 2

        # Check category names and repo counts
        category_dict = dict(categories)
        assert "Web Application" in category_dict
        assert "Python Package" in category_dict
        assert len(category_dict["Web Application"]) == 1
        assert len(category_dict["Python Package"]) == 1

    def test_group_by_category_with_ordering(self):
        """Test category ordering based on theme preferences."""
        repos_data = [
            {"name": "repo1", "category": "Other Tool"},
            {"name": "repo2", "category": "Web Application"},
            {"name": "repo3", "category": "Python Package"},
        ]

        generator = SiteGenerator()
        theme_config = generator.themes["educational"]

        categories = generator._group_by_category(repos_data, theme_config)

        # Should follow educational theme order
        category_names = [cat[0] for cat in categories]

        # Web Application should come before Python Package (per educational order)
        web_index = category_names.index("Web Application")
        python_index = category_names.index("Python Package")
        other_index = category_names.index("Other Tool")

        assert web_index < python_index
        # Other Tool should come last (not in preferred order)
        assert other_index > python_index

    def test_generate_category_buttons(self, sample_extracted_repos):
        """Test category button generation."""
        generator = SiteGenerator()
        theme_config = generator.themes["portfolio"]
        categories = generator._group_by_category(sample_extracted_repos, theme_config)

        buttons_html = generator._generate_category_buttons(categories, theme_config)

        assert "Web Application" in buttons_html
        assert "Python Package" in buttons_html
        assert "onclick=\"filterByCategory('web-application')\"" in buttons_html
        assert "onclick=\"filterByCategory('python-package')\"" in buttons_html
        assert f"bg-{theme_config['accent_color']}" in buttons_html

    def test_generate_repo_cards(self, sample_extracted_repos):
        """Test repository card generation."""
        generator = SiteGenerator()
        theme_config = generator.themes["resume"]
        metadata = {
            "web-app": {"icon": "🌐", "key_features": ["Feature 1", "Feature 2"]}
        }

        cards_html = generator._generate_repo_cards(
            repos=sample_extracted_repos[:1],  # Just web-app
            category_id="web-application",
            theme_config=theme_config,
            metadata=metadata,
        )

        assert "web-app" in cards_html
        assert "A React web application" in cards_html
        assert "🌐" in cards_html
        assert "Feature 1" in cards_html
        assert "45" in cards_html  # stars
        assert "12" in cards_html  # forks
        assert "JavaScript" in cards_html
        assert "MIT" in cards_html

    def test_generate_repo_cards_sorting(self):
        """Test repository cards are sorted by stars."""
        repos = [
            {
                "name": "low-stars",
                "url": "https://github.com/user/low-stars",
                "stars": 5,
                "stargazers_count": 5,
                "forks": 1,
            },
            {
                "name": "high-stars",
                "url": "https://github.com/user/high-stars",
                "stars": 100,
                "stargazers_count": 100,
                "forks": 20,
            },
            {
                "name": "medium-stars",
                "url": "https://github.com/user/medium-stars",
                "stars": 50,
                "stargazers_count": 50,
                "forks": 10,
            },
        ]

        generator = SiteGenerator()
        theme_config = generator.themes["portfolio"]

        cards_html = generator._generate_repo_cards(
            repos=repos, category_id="test", theme_config=theme_config, metadata={}
        )

        # Check order by finding positions in HTML
        high_pos = cards_html.find("high-stars")
        medium_pos = cards_html.find("medium-stars")
        low_pos = cards_html.find("low-stars")

        assert high_pos < medium_pos < low_pos

    def test_generate_topics_html(self):
        """Test topics HTML generation."""
        generator = SiteGenerator()
        theme_config = {"accent_color": "blue"}

        topics = ["python", "cli", "tool", "testing", "automation"]
        topics_html = generator._generate_topics_html(topics, theme_config)

        assert "python" in topics_html
        assert "cli" in topics_html
        assert "bg-blue-50" in topics_html
        assert "text-blue-600" in topics_html
        assert topics_html.count("<span") == 5  # Should have 5 topic spans

    def test_generate_topics_html_empty(self):
        """Test topics HTML generation with empty topics."""
        generator = SiteGenerator()
        theme_config = {"accent_color": "blue"}

        topics_html = generator._generate_topics_html([], theme_config)
        assert topics_html == ""

    def test_generate_topics_html_limit(self):
        """Test topics HTML generation limits to 5 topics."""
        generator = SiteGenerator()
        theme_config = {"accent_color": "green"}

        topics = ["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7"]
        topics_html = generator._generate_topics_html(topics, theme_config)

        # Should only show first 5 topics
        assert topics_html.count("<span") == 5
        assert "topic1" in topics_html
        assert "topic5" in topics_html
        assert "topic6" not in topics_html

    def test_generate_javascript(self):
        """Test JavaScript generation."""
        generator = SiteGenerator()
        theme_config = {"accent_color": "purple"}

        js_html = generator._generate_javascript(theme_config)

        assert "<script>" in js_html
        assert "</script>" in js_html
        assert "searchInput" in js_html
        assert "filterByCategory" in js_html
        assert "bg-purple-600" in js_html  # Should use theme accent color
        assert "searchableText" in js_html

    def test_all_themes_work(self, tmp_path, sample_extracted_repos):
        """Test that all themes generate valid HTML."""
        generator = SiteGenerator()

        for theme_name in generator.themes.keys():
            output_file = tmp_path / f"{theme_name}_site.html"

            generator.generate_site(
                repos_data=sample_extracted_repos,
                theme=theme_name,
                output_file=str(output_file),
            )

            assert output_file.exists()
            content = output_file.read_text()

            # Basic HTML validation
            assert "<!DOCTYPE html>" in content
            assert "<html" in content
            assert "</html>" in content
            assert "<head>" in content
            assert "<body" in content

            # Theme-specific content
            theme_config = generator.themes[theme_name]
            assert theme_config["title"] in content
            assert theme_config["description"] in content

    def test_repo_content_is_html_escaped(self, tmp_path):
        """Repo-supplied text and URLs must not inject HTML/JS into the site."""
        repos = [
            {
                "name": "evil<img src=x onerror=alert(1)>",
                "description": '"><script>alert(2)</script>',
                "url": "javascript:alert(3)",
                "homepage": "javascript:alert(4)",
                "pages_url": "https://ok.github.io/x/",
                "stars": 1,
                "forks": 1,
                "category": "Other Tool'); alert(5); //",
                "topics": ["<b>topic</b>"],
                "languages": ["<i>Py</i>"],
                "license": "<u>MIT</u>",
                "download_links": {"windows": "javascript:alert(6)"},
                "latest_version": {"tag": "<svg onload=alert(7)>"},
            }
        ]

        generator = SiteGenerator()
        output_file = tmp_path / "xss_site.html"
        generator.generate_site(repos, theme="portfolio", output_file=str(output_file))

        content = output_file.read_text()

        for payload in [
            "<img src=x",
            "<script>alert(2)",
            'href="javascript:',
            "alert(5); //')",
            "<svg onload",
            "<b>topic</b>",
            "<i>Py</i>",
            "<u>MIT</u>",
        ]:
            assert payload not in content

        # Escaped text is still rendered; unsafe URLs are defanged to '#'
        assert "&lt;img src=x" in content
        assert 'href="#"' in content
        assert 'href="https://ok.github.io/x/"' in content

    def test_category_icons(self, sample_extracted_repos):
        """Test category icons are properly included."""
        generator = SiteGenerator()
        theme_config = generator.themes["educational"]
        categories = generator._group_by_category(sample_extracted_repos, theme_config)

        sections_html = generator._generate_category_sections(
            categories, theme_config, {}
        )

        # Check for expected icons
        assert "fa-globe" in sections_html  # Web Application icon
        assert "fa-python" in sections_html  # Python Package icon

    def test_confidence_indicator(self):
        """Test category confidence indicator display."""
        repos = [
            {
                "name": "low-confidence-repo",
                "url": "https://github.com/user/low-confidence-repo",
                "description": "Test repo",
                "category_confidence": 0.7,  # Below 0.8 threshold
                "stars": 10,
                "stargazers_count": 10,
                "forks": 2,
            }
        ]

        generator = SiteGenerator()
        theme_config = generator.themes["portfolio"]

        cards_html = generator._generate_repo_cards(
            repos=repos, category_id="test", theme_config=theme_config, metadata={}
        )

        assert "Category confidence: 70%" in cards_html
        assert "text-orange-600" in cards_html
