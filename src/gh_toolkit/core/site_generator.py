"""Site generation for repository portfolios."""

import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rich.console import Console

console = Console()


def _safe_url(url: Any) -> str:
    """Return the URL escaped for an href attribute, or '#' if not http(s).

    Repo metadata (homepage, release assets) is attacker-controllable, so
    reject anything that isn't a plain http/https URL (e.g. javascript:).
    """
    if not url or not isinstance(url, str):
        return "#"
    if urlparse(url).scheme not in ("http", "https"):
        return "#"
    return escape(url, quote=True)


def _category_id(category: str) -> str:
    """Build a DOM/JS-safe category id (used inside onclick handlers)."""
    return re.sub(r"[^a-z0-9-]", "", category.replace(" ", "-").lower())


class SiteGenerator:
    """Generate beautiful landing pages from repository data."""

    def __init__(self):
        """Initialize site generator."""
        self.themes = {
            "educational": self._get_educational_theme(),
            "resume": self._get_resume_theme(),
            "research": self._get_research_theme(),
            "portfolio": self._get_portfolio_theme(),
        }

    def generate_site(
        self,
        repos_data: list[dict[str, Any]],
        theme: str = "educational",
        output_file: str = "portfolio_site.html",
        metadata: dict[str, Any] | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        """Generate a complete landing page from repository data.

        Args:
            repos_data: List of repository data dictionaries
            theme: Theme name (educational, resume, research, portfolio)
            output_file: Output HTML file path
            metadata: Optional metadata for additional customization
            title: Optional custom title
            description: Optional custom description
        """
        if theme not in self.themes:
            raise ValueError(
                f"Unknown theme: {theme}. Available: {', '.join(self.themes.keys())}"
            )

        theme_config = self.themes[theme]
        metadata = metadata or {}

        # Use custom title/description or theme defaults
        site_title = title or theme_config["title"]
        site_description = description or theme_config["description"]

        # Group repositories by category
        categories = self._group_by_category(repos_data, theme_config)

        # Generate HTML
        html = self._generate_html(
            categories=categories,
            theme_config=theme_config,
            metadata=metadata,
            title=site_title,
            description=site_description,
        )

        # Save to file
        output_path = Path(output_file)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        console.print(f"[green]✓ Site generated: {output_path}[/green]")
        console.print(f"[blue]Theme: {theme}[/blue]")
        console.print(f"[blue]Repositories: {len(repos_data)}[/blue]")
        console.print(f"[blue]Categories: {len(categories)}[/blue]")

    def _group_by_category(
        self, repos_data: list[dict[str, Any]], theme_config: dict[str, Any]
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """Group repositories by category according to theme preferences."""
        categories: dict[str, list[dict[str, Any]]] = {}

        for repo in repos_data:
            cat = repo.get("category", "Other Tool")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(repo)

        # Sort according to theme's preferred order
        category_order = theme_config.get("category_order", [])
        ordered_categories: list[tuple[str, list[dict[str, Any]]]] = []

        # Add categories in preferred order
        for cat in category_order:
            if cat in categories:
                ordered_categories.append((cat, categories[cat]))

        # Add remaining categories
        for cat, repos in categories.items():
            if cat not in category_order:
                ordered_categories.append((cat, repos))

        return ordered_categories

    def _generate_html(
        self,
        categories: list[tuple[str, list[dict[str, Any]]]],
        theme_config: dict[str, Any],
        metadata: dict[str, Any],
        title: str,
        description: str,
    ) -> str:
        """Generate complete HTML document."""
        title = escape(title)
        description = escape(description)

        # Start building HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        {theme_config["custom_css"]}
    </style>
</head>
<body class="{theme_config["body_class"]}">
    <!-- Header -->
    <header class="{theme_config["header_class"]}">
        <div class="container mx-auto px-4">
            <h1 class="text-5xl font-bold mb-4">{title}</h1>
            <p class="text-xl opacity-90">{description}</p>
        </div>
    </header>

    <!-- Search Bar -->
    <section class="bg-white py-6 shadow-sm sticky top-0 z-20">
        <div class="container mx-auto px-4">
            <div class="max-w-2xl mx-auto">
                <div class="relative">
                    <input type="text" id="searchInput" placeholder="Search by name, description, or topic..."
                           class="w-full px-4 py-3 pl-12 text-gray-700 bg-gray-50 border border-gray-300 rounded-lg focus:outline-none focus:border-{theme_config["accent_color"]}-500 focus:bg-white">
                    <i class="fas fa-search absolute left-4 top-4 text-gray-400"></i>
                </div>
                <div id="searchResults" class="mt-2 text-sm text-gray-600"></div>
            </div>
        </div>
    </section>

    <!-- Category Navigation -->
    <nav class="bg-gray-50 py-4 border-b">
        <div class="container mx-auto px-4">
            <div class="flex flex-wrap gap-2 justify-center">
                <button onclick="filterByCategory('all')" class="category-btn px-4 py-2 bg-{theme_config["accent_color"]}-600 text-white rounded-full hover:bg-{theme_config["accent_color"]}-700 transition" data-category="all">All Projects</button>
                {self._generate_category_buttons(categories, theme_config)}
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="container mx-auto px-4 py-12">
        {self._generate_category_sections(categories, theme_config, metadata)}
    </main>

    <!-- Footer -->
    <footer class="{theme_config["footer_class"]}">
        <div class="container mx-auto px-4 text-center">
            <p class="mb-2">{title}</p>
            <p class="text-sm opacity-75">Last updated: {datetime.now().strftime("%B %d, %Y")}</p>
            <div class="mt-4">
                <a href="https://github.com" class="text-white hover:text-gray-200 mx-2">
                    <i class="fab fa-github text-2xl"></i>
                </a>
            </div>
        </div>
    </footer>

    {self._generate_javascript(theme_config)}
</body>
</html>"""

        return html

    def _generate_category_buttons(
        self,
        categories: list[tuple[str, list[dict[str, Any]]]],
        theme_config: dict[str, Any],
    ) -> str:
        """Generate category filter buttons."""
        buttons: list[str] = []
        for cat, _ in categories:
            cat_id = _category_id(cat)
            button = f'''<button onclick="filterByCategory('{cat_id}')" class="category-btn px-4 py-2 bg-{theme_config["accent_color"]}-100 text-{theme_config["accent_color"]}-700 rounded-full hover:bg-{theme_config["accent_color"]}-200 transition" data-category="{cat_id}">{escape(cat)}</button>'''
            buttons.append(button)
        return " ".join(buttons)

    def _generate_category_sections(
        self,
        categories: list[tuple[str, list[dict[str, Any]]]],
        theme_config: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str:
        """Generate category sections with repository cards."""
        sections: list[str] = []

        category_icons = theme_config.get("category_icons", {})

        for category, cat_repos in categories:
            cat_id = _category_id(category)
            icon = category_icons.get(category, "fa-folder")

            section = f'''
        <section id="{cat_id}" class="mb-16">
            <div class="flex items-center mb-8">
                <i class="fas {icon} text-4xl text-{theme_config["accent_color"]}-600 mr-4"></i>
                <h2 class="text-3xl font-bold text-gray-800">{escape(category)}</h2>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {self._generate_repo_cards(cat_repos, cat_id, theme_config, metadata)}
            </div>
        </section>'''

            sections.append(section)

        return "\n".join(sections)

    def _generate_repo_cards(
        self,
        repos: list[dict[str, Any]],
        category_id: str,
        theme_config: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str:
        """Generate repository cards."""
        cards: list[str] = []

        # Sort repositories by stars
        sorted_repos = sorted(repos, key=lambda x: x.get("stars", 0), reverse=True)

        for repo in sorted_repos:
            repo_name = repo["name"]
            repo_meta = metadata.get(repo_name, {})
            icon_emoji = escape(
                repo_meta.get("icon", theme_config.get("default_icon", "🔧"))
            )

            # Build features list
            features_html = ""
            if "key_features" in repo_meta:
                features_html = '<ul class="mt-2 space-y-1">'
                for feature in repo_meta["key_features"][:3]:
                    features_html += f'<li class="text-sm text-gray-600"><i class="fas fa-check text-green-500 mr-1"></i>{escape(feature)}</li>'
                features_html += "</ul>"

            # Build download buttons
            download_html = ""
            if repo.get("download_links"):
                download_html = '<div class="mt-3">'
                if repo.get("latest_version"):
                    version = repo["latest_version"]
                    download_html += f'<div class="text-xs text-gray-500 mb-1">Version {escape(str(version["tag"]))}</div>'
                download_html += '<div class="flex gap-2">'
                for platform, link in repo["download_links"].items():
                    platform_icon = {
                        "windows": "fa-windows",
                        "mac": "fa-apple",
                        "linux": "fa-linux",
                    }.get(platform, "fa-download")
                    download_html += f'<a href="{_safe_url(link)}" class="text-sm px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-full transition"><i class="fab {platform_icon}"></i></a>'
                download_html += "</div></div>"

            # Build confidence indicator
            confidence_html = ""
            if repo.get("category_confidence", 1.0) < 0.8:
                confidence = repo["category_confidence"]
                confidence_html = f'<div class="text-xs text-orange-600 mb-2">Category confidence: {confidence:.0%}</div>'

            # Build main card (all repo-supplied text is escaped — repository
            # names, descriptions, and topics are attacker-controllable)
            card = f'''
                <div class="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition duration-300 repo-card"
                     data-category="{category_id}"
                     data-name="{escape(repo["name"].lower(), quote=True)}"
                     data-description="{escape((repo.get("description") or "").lower(), quote=True)}"
                     data-topics="{escape(" ".join(repo.get("topics", [])).lower(), quote=True)}">

                    {confidence_html}

                    <div class="flex items-start justify-between mb-3">
                        <h3 class="text-xl font-semibold text-gray-800 flex items-center">
                            <span class="text-2xl mr-2">{icon_emoji}</span>
                            <span class="repo-name">{escape(repo["name"])}</span>
                        </h3>
                        <div class="text-right">
                            <div class="flex items-center text-sm text-gray-600">
                                <i class="fas fa-star text-yellow-500 mr-1"></i>
                                {repo.get("stars", 0)}
                            </div>
                            {f'<div class="text-xs text-gray-500 mt-1"><i class="fas fa-code-branch mr-1"></i>{repo.get("forks", 0)}</div>' if repo.get("forks") else ""}
                        </div>
                    </div>

                    <p class="text-gray-600 mb-3 repo-description">{escape(repo.get("description") or "No description available")}</p>

                    {features_html}

                    <div class="mt-4 flex flex-wrap gap-2">
                        <a href="{_safe_url(repo["url"])}" class="text-sm px-3 py-1 bg-{theme_config["accent_color"]}-100 text-{theme_config["accent_color"]}-700 rounded-full hover:bg-{theme_config["accent_color"]}-200">
                            <i class="fab fa-github mr-1"></i>GitHub
                        </a>
                        {f'<a href="{_safe_url(repo["homepage"])}" class="text-sm px-3 py-1 bg-blue-100 text-blue-700 rounded-full hover:bg-blue-200"><i class="fas fa-globe mr-1"></i>Website</a>' if repo.get("homepage") else ""}
                        {f'<a href="{_safe_url(repo["pages_url"])}" class="text-sm px-3 py-1 bg-green-100 text-green-700 rounded-full hover:bg-green-200"><i class="fas fa-book-open mr-1"></i>Docs</a>' if repo.get("pages_url") else ""}
                    </div>

                    {download_html}

                    {self._generate_topics_html(repo.get("topics", []), theme_config)}

                    <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
                        <div class="flex gap-3">
                            {" ".join([f'<span class="px-2 py-1 bg-gray-100 text-gray-600 rounded">{escape(lang)}</span>' for lang in repo.get("languages", [])[:3]])}
                        </div>
                        {f'<span class="text-green-600"><i class="fas fa-balance-scale mr-1"></i>{escape(repo.get("license", ""))}</span>' if repo.get("license") else ""}
                    </div>
                </div>'''

            cards.append(card)

        return "\n".join(cards)

    def _generate_topics_html(
        self, topics: list[str], theme_config: dict[str, Any]
    ) -> str:
        """Generate HTML for repository topics."""
        if not topics:
            return ""

        accent_color = theme_config["accent_color"]
        topic_tags: list[str] = []
        for topic in topics[:5]:  # Limit to 5 topics
            topic_tags.append(
                f'<span class="text-xs px-2 py-1 bg-{accent_color}-50 text-{accent_color}-600 rounded-full">#{escape(topic)}</span>'
            )

        return f'<div class="mt-2 flex flex-wrap gap-1">{" ".join(topic_tags)}</div>'

    def _generate_javascript(self, theme_config: dict[str, Any]) -> str:
        """Generate JavaScript for search and filtering."""
        accent_color = theme_config["accent_color"]

        return f"""
    <script>
        // Search and filter functionality
        const searchInput = document.getElementById('searchInput');
        const searchResults = document.getElementById('searchResults');
        const allCards = document.querySelectorAll('.repo-card');
        let currentCategory = 'all';

        searchInput.addEventListener('input', function(e) {{
            const searchTerms = e.target.value.toLowerCase()
                .split(' ')
                .filter(term => term.length > 0);

            let visibleCount = 0;

            allCards.forEach(card => {{
                const searchableText =
                    card.dataset.name + ' ' +
                    card.dataset.description + ' ' +
                    card.dataset.topics;

                const matchesSearch = searchTerms.length === 0 ||
                    searchTerms.every(term => searchableText.includes(term));

                const matchesCategory = currentCategory === 'all' ||
                    card.dataset.category === currentCategory;

                if (matchesSearch && matchesCategory) {{
                    card.style.display = 'block';
                    visibleCount++;
                }} else {{
                    card.style.display = 'none';
                }}
            }});

            if (searchTerms.length > 0) {{
                const termText = searchTerms.length === 1 ? 'term' : 'terms';
                searchResults.textContent =
                    `Found ${{visibleCount}} project${{visibleCount !== 1 ? 's' : ''}} matching all ${{termText}}`;
            }} else {{
                searchResults.textContent = '';
            }}
        }});

        function filterByCategory(category) {{
            currentCategory = category;

            // Update button styles
            document.querySelectorAll('.category-btn').forEach(btn => {{
                if (btn.dataset.category === category) {{
                    btn.className = 'category-btn px-4 py-2 bg-{accent_color}-600 text-white rounded-full hover:bg-{accent_color}-700 transition';
                }} else {{
                    btn.className = 'category-btn px-4 py-2 bg-{accent_color}-100 text-{accent_color}-700 rounded-full hover:bg-{accent_color}-200 transition';
                }}
            }});

            // Filter cards
            let visibleCount = 0;

            allCards.forEach(card => {{
                const searchableText =
                    card.dataset.name + ' ' +
                    card.dataset.description + ' ' +
                    card.dataset.topics;

                const searchTerms = searchInput.value.toLowerCase()
                    .split(' ')
                    .filter(term => term.length > 0);

                const matchesCategory = category === 'all' || card.dataset.category === category;
                const matchesSearch = searchTerms.length === 0 ||
                    searchTerms.every(term => searchableText.includes(term));

                if (matchesCategory && matchesSearch) {{
                    card.style.display = 'block';
                    visibleCount++;
                }} else {{
                    card.style.display = 'none';
                }}
            }});

            // Smooth scroll to results
            document.querySelector('main').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}

        // Enhanced highlighting
        const escapeHtml = text => text.replace(/[&<>"']/g, c => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[c]));
        const escapeRegex = text => text.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
        searchInput.addEventListener('input', function(e) {{
            const searchTerms = e.target.value.toLowerCase()
                .split(' ')
                .filter(term => term.length > 2);

            document.querySelectorAll('.repo-name, .repo-description').forEach(elem => {{
                // Escape before innerHTML so literal HTML in repo text stays inert
                let html = escapeHtml(elem.textContent);

                if (searchTerms.length > 0) {{
                    searchTerms.forEach(term => {{
                        const regex = new RegExp(`(${{escapeRegex(escapeHtml(term))}})`, 'gi');
                        html = html.replace(regex, '<mark class="bg-yellow-200">$1</mark>');
                    }});
                }}
                elem.innerHTML = html;
            }});
        }});
    </script>"""

    def _get_educational_theme(self) -> dict[str, Any]:
        """Get educational theme configuration."""
        return {
            "title": "Educational Tools Collection",
            "description": "A comprehensive suite of tools for teaching, learning, and educational content creation",
            "accent_color": "purple",
            "body_class": "bg-gray-50",
            "header_class": "bg-gradient-to-r from-purple-600 to-purple-800 text-white py-16",
            "footer_class": "bg-gradient-to-r from-purple-600 to-purple-800 text-white py-8 mt-16",
            "default_icon": "🎓",
            "custom_css": """
                .card-hover:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
                }
            """,
            "category_order": [
                "Desktop Application",
                "Web Application",
                "Python Package",
                "Learning Resource",
                "Infrastructure Tool",
                "Notebook/Analysis",
                "Other Tool",
            ],
            "category_icons": {
                "Desktop Application": "fa-desktop",
                "Python Package": "fa-python",
                "Learning Resource": "fa-graduation-cap",
                "Web Application": "fa-globe",
                "Infrastructure Tool": "fa-tools",
                "Notebook/Analysis": "fa-chart-bar",
                "Other Tool": "fa-puzzle-piece",
            },
        }

    def _get_resume_theme(self) -> dict[str, Any]:
        """Get resume/portfolio theme configuration."""
        return {
            "title": "Professional Portfolio",
            "description": "A showcase of professional projects and technical expertise",
            "accent_color": "blue",
            "body_class": "bg-gray-50",
            "header_class": "bg-gradient-to-r from-blue-600 to-blue-800 text-white py-16",
            "footer_class": "bg-gradient-to-r from-blue-600 to-blue-800 text-white py-8 mt-16",
            "default_icon": "💼",
            "custom_css": """
                .card-hover:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 15px 25px -5px rgba(0, 0, 0, 0.15);
                }
            """,
            "category_order": [
                "Web Application",
                "Desktop Application",
                "Python Package",
                "Infrastructure Tool",
                "Notebook/Analysis",
                "Learning Resource",
                "Other Tool",
            ],
            "category_icons": {
                "Web Application": "fa-globe",
                "Desktop Application": "fa-desktop",
                "Python Package": "fa-python",
                "Infrastructure Tool": "fa-cogs",
                "Notebook/Analysis": "fa-chart-line",
                "Learning Resource": "fa-book",
                "Other Tool": "fa-code",
            },
        }

    def _get_research_theme(self) -> dict[str, Any]:
        """Get research theme configuration."""
        return {
            "title": "Research Portfolio",
            "description": "Academic research projects, publications, and scientific computing tools",
            "accent_color": "green",
            "body_class": "bg-gray-50",
            "header_class": "bg-gradient-to-r from-green-600 to-green-800 text-white py-16",
            "footer_class": "bg-gradient-to-r from-green-600 to-green-800 text-white py-8 mt-16",
            "default_icon": "🔬",
            "custom_css": """
                .card-hover:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px -5px rgba(0, 0, 0, 0.1);
                }
            """,
            "category_order": [
                "Learning Resource",
                "Notebook/Analysis",
                "Python Package",
                "Web Application",
                "Infrastructure Tool",
                "Desktop Application",
                "Other Tool",
            ],
            "category_icons": {
                "Learning Resource": "fa-book-open",
                "Notebook/Analysis": "fa-chart-area",
                "Python Package": "fa-python",
                "Web Application": "fa-globe",
                "Infrastructure Tool": "fa-server",
                "Desktop Application": "fa-desktop",
                "Other Tool": "fa-flask",
            },
        }

    def _get_portfolio_theme(self) -> dict[str, Any]:
        """Get general portfolio theme configuration."""
        return {
            "title": "Project Portfolio",
            "description": "A collection of software projects and development work",
            "accent_color": "indigo",
            "body_class": "bg-gray-50",
            "header_class": "bg-gradient-to-r from-indigo-600 to-indigo-800 text-white py-16",
            "footer_class": "bg-gradient-to-r from-indigo-600 to-indigo-800 text-white py-8 mt-16",
            "default_icon": "🚀",
            "custom_css": """
                .card-hover:hover {
                    transform: translateY(-4px);
                    box-shadow: 0 20px 30px -10px rgba(0, 0, 0, 0.15);
                }
            """,
            "category_order": [
                "Web Application",
                "Desktop Application",
                "Python Package",
                "Infrastructure Tool",
                "Learning Resource",
                "Notebook/Analysis",
                "Other Tool",
            ],
            "category_icons": {
                "Web Application": "fa-globe",
                "Desktop Application": "fa-window-maximize",
                "Python Package": "fa-python",
                "Infrastructure Tool": "fa-tools",
                "Learning Resource": "fa-book",
                "Notebook/Analysis": "fa-chart-bar",
                "Other Tool": "fa-code-branch",
            },
        }
