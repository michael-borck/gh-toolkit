"""Page generator for converting README.md files to HTML or Jekyll markdown."""

import html
import re
from typing import Any

import yaml

try:
    import mistune
except ImportError as e:
    raise ImportError(
        "The 'mistune' library is required. Please install it: pip install mistune"
    ) from e


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {styles_and_scripts}
</head>
<body class="bg-stone-50 dark:bg-stone-900 text-stone-800 dark:text-stone-200 leading-relaxed transition-colors duration-300">
    {header}
    <main>
        {hero}
        {main_content}
    </main>
    {footer}
    <script>
        {javascript}
    </script>
</body>
</html>
"""

STYLES_AND_SCRIPTS_BLOCK = """
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: { sans: ['Inter', 'sans-serif'], },
                    colors: {
                        'stone': { '50': '#fafaf9', '100': '#f5f5f4', '200': '#e7e5e4', '300': '#d6d3d1', '400': '#a8a29e', '500': '#78716c', '600': '#57534e', '700': '#44403c', '800': '#292524', '900': '#1c1917', '950': '#0c0a09' },
                        'sky': { '100': '#e0f2fe', '400':'#38bdf8', '500': '#0ea5e9', '600': '#0284c7', '700': '#0369a1', '800': '#075985' },
                        'green': { '600': '#16a34a', '700': '#15803d'},
                    }
                }
            }
        }
    </script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        .code-block { position: relative; }
        .copy-button { position: absolute; top: 0.75rem; right: 0.75rem; padding: 0.25rem 0.5rem; font-size: 0.75rem; border-radius: 0.375rem; background-color: #44403c; color: white; cursor: pointer; opacity: 0; transition: opacity 0.2s ease-in-out, background-color 0.2s; }
        .code-block:hover .copy-button { opacity: 1; }
        .copy-button:hover { background-color: #292524; }
        html.dark .copy-button { background-color: #1c1917; }
        html.dark .copy-button:hover { background-color: #292524; }
        .api-tab { padding: 1rem 0.25rem; margin-bottom: -2px; border-bottom-width: 2px; font-weight: 500; font-size: 0.875rem; line-height: 1.25rem; border-color: transparent; color: #57534e; transition: all 0.2s; }
        .api-tab:hover { border-color: #d6d3d1; color: #44403c; }
        .api-tab.active-tab { border-color: #0284c7; color: #0284c7; }
        html.dark .api-tab { color: #a8a29e; }
        html.dark .api-tab:hover { border-color: #57534e; color: #e7e5e4; }
        html.dark .api-tab.active-tab { border-color: #0ea5e9; color: #0ea5e9; }
        .prose-styles h1, .prose-styles h2, .prose-styles h3 { margin-top: 1.5em; margin-bottom: 0.8em; }
        .prose-styles p { margin-bottom: 1em; line-height: 1.7; }
        .prose-styles ul { list-style-type: disc; margin-left: 1.5em; margin-bottom: 1em; }
        .prose-styles li { margin-bottom: 0.5em; }
        .prose-styles a { color: #0284c7; text-decoration: underline; }
        .prose-styles a:hover { color: #0369a1; }
        .prose-styles code { font-family: monospace; background-color: #e7e5e4; color: #be185d; padding: 0.2em 0.4em; border-radius: 3px; }
        .prose-styles pre > code { background-color: transparent; padding: 0; }
        html.dark .prose-styles a { color: #38bdf8; }
        html.dark .prose-styles a:hover { color: #7dd3fc; }
        html.dark .prose-styles code { background-color: #44403c; color: #f9a8d4;}
    </style>
"""


class BadgeRemoverRenderer(mistune.HTMLRenderer):
    """Custom renderer that removes shield.io badges from markdown."""

    def image(self, text: str, url: str, title: str | None = None) -> str:
        """Remove shield.io badges, keep other images."""
        if "img.shields.io" in url:
            return ""
        return super().image(text, url, title)


class PageGenerator:
    """Generates HTML or Jekyll markdown pages from README.md content."""

    def __init__(self, markdown_text: str):
        """Initialize the page generator with markdown content."""
        self.markdown_text = markdown_text
        self.sections: list[dict[str, Any]] = []
        self.title = "Project Landing Page"
        self.description = ""
        self.links: dict[str, dict[str, str]] = {}

        renderer = BadgeRemoverRenderer()
        self.md_parser = mistune.create_markdown(
            renderer=renderer, plugins=["task_lists", "strikethrough"]
        )

    def _find_link_with_label(
        self, key: str, url_pattern: str, default_label: str
    ) -> None:
        """Extract links with labels from markdown text."""
        full_pattern = re.compile(
            rf"\[(?:!\[([\w\s.'-]+)\]\(.*?\)|([\w\s.'-]+))\]\s*\(\s*({url_pattern})\s*\)",
            re.IGNORECASE,
        )
        match = full_pattern.search(self.markdown_text)
        if match:
            label = match.group(1) or match.group(2)
            url = match.group(3)
            self.links[key] = {
                "url": url.strip(),
                "label": label.strip() if label else default_label,
            }
        else:
            raw_match = re.search(url_pattern, self.markdown_text, re.IGNORECASE)
            if raw_match:
                self.links[key] = {
                    "url": raw_match.group(0).strip(),
                    "label": default_label,
                }

    def _extract_links(self) -> None:
        """Extract various types of links from the markdown."""
        self._find_link_with_label(
            key="repo",
            url_pattern=r"https?://github\.com/[\w.-]+/[\w.-]+",
            default_label="View on GitHub",
        )
        self._find_link_with_label(
            key="template",
            url_pattern=r"https?://github\.com/[\w.-]+/[\w.-]+/generate",
            default_label="Use this Template",
        )
        self._find_link_with_label(
            key="docs",
            url_pattern=r"https?://[\w.-]+\.github\.io[\w./-]*",
            default_label="View Docs",
        )
        self._find_link_with_label(
            key="gitingest",
            url_pattern=r"https?://gitingest\.com/[\w./-]+",
            default_label="LLM Ingest",
        )
        self._find_link_with_label(
            key="deepwiki",
            url_pattern=r"https?://deepwiki\.com/[\w./-]+",
            default_label="Deep Wiki",
        )

    def _extract_title_and_description(self) -> None:
        """Extract title and description from markdown content."""
        # Extract title from first H1
        h1_match = re.search(r"^#\s(.+)", self.markdown_text, flags=re.MULTILINE)
        if h1_match:
            self.title = h1_match.group(1).strip()

        # Extract description from first paragraph after title
        # Remove the H1 line and get the first non-empty line
        lines = self.markdown_text.split("\n")
        found_title = False
        for line in lines:
            line = line.strip()
            if not found_title and line.startswith("# "):
                found_title = True
                continue
            if found_title and line and not line.startswith("#"):
                # Skip badge lines, lists, and other markdown elements
                if not any(
                    x in line
                    for x in [
                        "![",
                        "[![",
                        "**",
                        "##",
                        "- ",
                        "* ",
                        "1. ",
                        "2. ",
                        "3. ",
                        "4. ",
                        "5. ",
                        "6. ",
                        "7. ",
                        "8. ",
                        "9. ",
                    ]
                ):
                    self.description = line
                    break

    def parse_markdown(self) -> None:
        """Parse the markdown content into sections."""
        self._extract_links()
        self._extract_title_and_description()

        parts = re.split(r"(^##\s.*)", self.markdown_text, flags=re.MULTILINE)

        hero_content = parts[0]
        h1_match = re.search(r"^#\s(.*)", hero_content, flags=re.MULTILINE)
        if h1_match:
            hero_content = hero_content.replace(h1_match.group(0), "", 1)

        self.sections.append(
            {
                "type": "hero",
                "title": self.title,
                "content": self.md_parser(hero_content.strip()),
            }
        )

        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                title = parts[i].strip().replace("## ", "")
                content = parts[i + 1].strip()
                self.sections.append(
                    {
                        "title": title,
                        "content_html": self.md_parser(content),
                    }
                )

    def render_html(self) -> str:
        """Render as a complete HTML page."""
        hero_section = next((s for s in self.sections if s["type"] == "hero"), None)
        main_content_sections = [s for s in self.sections if "type" not in s]

        hero_html = self._render_hero(hero_section, self.links)
        main_content_html = "\n".join(
            [self._render_section(s, i) for i, s in enumerate(main_content_sections)]
        )
        header_html = self._render_header(main_content_sections)
        ack_section = next(
            (s for s in main_content_sections if "license" in s["title"].lower()),
            None,
        )
        footer_html = self._render_footer(ack_section)

        return HTML_TEMPLATE.format(
            title=html.escape(self.title),
            styles_and_scripts=STYLES_AND_SCRIPTS_BLOCK,
            header=header_html,
            hero=hero_html,
            main_content=main_content_html,
            footer=footer_html,
            javascript=self._get_javascript(),
        )

    def render_jekyll(self) -> str:
        """Render as Jekyll markdown with front matter."""
        # Generate the HTML first to get the body content
        html_content = self.render_html()

        # Extract content between body tags
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html_content, re.DOTALL)
        if not body_match:
            raise ValueError("Could not extract body content from HTML")

        body_content = body_match.group(1).strip()

        # Create Jekyll front matter
        front_matter = {
            "layout": "default",
            "title": self.title,
        }

        if self.description:
            front_matter["description"] = self.description

        # Generate YAML front matter
        yaml_front_matter = yaml.dump(
            front_matter, default_flow_style=False, allow_unicode=True
        ).strip()

        return f"---\n{yaml_front_matter}\n---\n\n{body_content}"

    def _render_section(self, section: dict[str, Any], index: int) -> str:
        """Render a content section."""
        section_id = self._slugify(section["title"])
        bg_class = (
            "bg-white dark:bg-stone-800"
            if index % 2 == 0
            else "bg-stone-50 dark:bg-stone-900"
        )
        title_html = f'<h2 class="text-3xl font-bold tracking-tight text-stone-900 dark:text-white sm:text-4xl">{html.escape(section["title"])}</h2>'

        content_html = ""
        lower_title = section["title"].lower()

        if "feature" in lower_title:
            items = re.findall(r"<li>(.*?)</li>", section["content_html"], re.DOTALL)
            items_html = ""
            for item in items:
                clean_item = re.sub("<[^<]+?>", "", item).strip()
                title_match = re.search(r"<strong>(.*?)</strong>", item)
                card_title = (
                    title_match.group(1) if title_match else clean_item.split(":")[0]
                )
                card_content = (
                    clean_item.replace(card_title, "", 1)
                    .removeprefix(": ")
                    .removeprefix("** ")
                )
                items_html += f"""
                <div class="p-6 bg-stone-100 dark:bg-stone-950 rounded-lg border border-stone-200 dark:border-stone-700">
                    <h3 class="text-lg font-semibold text-stone-900 dark:text-white">{html.escape(card_title)}</h3>
                    <p class="mt-2 text-stone-600 dark:text-stone-400">{html.escape(card_content)}</p>
                </div>"""
            content_html = f'<div class="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-3">{items_html}</div>'
        else:
            content_html = f'<div class="mt-8 max-w-4xl mx-auto text-left prose-styles">{section["content_html"]}</div>'

        return f"""
        <section id="{section_id}" class="py-16 sm:py-20 lg:py-24 {bg_class}">
            <div class="container mx-auto px-4 sm:px-6 lg:px-8">
                <div class="text-center">{title_html}</div>
                {content_html}
            </div>
        </section>"""

    def _render_hero(
        self, hero: dict[str, Any] | None, links: dict[str, dict[str, str]]
    ) -> str:
        """Render the hero section."""
        if not hero:
            return ""

        title, content_html = hero.get("title", "Welcome"), hero.get("content", "")

        buttons: list[str] = []
        if links.get("template"):
            link = links["template"]
            buttons.append(
                f'<a href="{link["url"]}" target="_blank" class="inline-flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-6 rounded-lg shadow-lg transition-transform transform hover:scale-105">{html.escape(link["label"])}</a>'
            )

        # The 'Get Started' button should link to the first real section
        first_section_slug = (
            "#" + self._slugify(self.sections[1]["title"])
            if len(self.sections) > 1
            else ""
        )
        buttons.append(
            f'<a href="{first_section_slug}" class="inline-block rounded-lg bg-sky-600 px-8 py-3 text-base font-semibold text-white shadow-sm hover:bg-sky-700 transition-colors">Get Started</a>'
        )

        if links.get("docs"):
            link = links["docs"]
            buttons.append(
                f'<a href="{link["url"]}" target="_blank" class="inline-flex items-center justify-center bg-white dark:bg-stone-700 px-6 py-3 text-base font-semibold text-sky-600 dark:text-sky-400 shadow-sm ring-1 ring-inset ring-stone-300 dark:ring-stone-600 hover:bg-stone-100 dark:hover:bg-stone-600 transition-colors rounded-lg">{html.escape(link["label"])}</a>'
            )

        if links.get("gitingest"):
            link = links["gitingest"]
            buttons.append(
                f'<a href="{link["url"]}" target="_blank" class="inline-flex items-center justify-center bg-sky-700 hover:bg-sky-800 text-white px-6 py-3 text-base font-semibold shadow-sm rounded-lg transition-colors">{html.escape(link["label"])}</a>'
            )

        if links.get("deepwiki"):
            link = links["deepwiki"]
            buttons.append(
                f'<a href="{link["url"]}" target="_blank" class="inline-flex items-center justify-center bg-stone-700 hover:bg-stone-800 text-white px-6 py-3 text-base font-semibold shadow-sm rounded-lg transition-colors">{html.escape(link["label"])}</a>'
            )

        buttons_html = "".join(buttons)

        return f"""<section class="py-20 sm:py-24 lg:py-32"><div class="container mx-auto px-4 sm:px-6 lg:px-8 text-center"><h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-stone-900 dark:text-white tracking-tight">{html.escape(title)}</h1><div class="mt-6 prose-styles max-w-3xl mx-auto">{content_html}</div><div class="mt-10 flex flex-wrap flex-col sm:flex-row justify-center items-center gap-4">{buttons_html}</div></div></section>"""

    def _slugify(self, text: str) -> str:
        """Convert text to a safe anchor slug.

        The result is interpolated into ``id`` and ``href`` attributes, so it
        must not contain quotes, angle brackets, or other HTML metacharacters.
        """
        slug = re.sub(r"[^a-z0-9+]+", "-", text.lower().strip()).strip("-")
        return slug or "section"

    def _render_header(self, sections: list[dict[str, Any]]) -> str:
        """Render the navigation header."""
        nav_links = [s["title"] for s in sections]
        desktop_links = "".join(
            f'<a href="#{self._slugify(link)}" class="text-stone-600 dark:text-stone-300 hover:text-sky-600 dark:hover:text-sky-500 px-3 py-2 rounded-md text-sm font-medium transition-colors">{html.escape(link)}</a>'
            for link in nav_links
        )
        mobile_links = "".join(
            f'<a href="#{self._slugify(link)}" class="text-stone-600 dark:text-stone-300 hover:text-sky-600 dark:hover:text-sky-500 hover:bg-stone-100 dark:hover:bg-stone-800 block px-3 py-2 rounded-md text-base font-medium">{html.escape(link)}</a>'
            for link in nav_links
        )
        repo_link = self.links.get("repo")
        github_button = (
            f'<a href="{repo_link["url"]}" target="_blank" class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-stone-800 hover:bg-stone-900 dark:bg-sky-600 dark:hover:bg-sky-700 transition-colors">{html.escape(repo_link["label"])}<span class="ml-2 font-bold text-lg leading-none">&#8594;</span></a>'
            if repo_link
            else ""
        )
        return f"""<header id="top" class="bg-white/90 dark:bg-stone-900/80 backdrop-blur-lg sticky top-0 z-50 shadow-sm"><div class="container mx-auto px-4 sm:px-6 lg:px-8"><nav class="flex items-center justify-between h-16"><div class="flex-shrink-0"><a href="#top" class="text-2xl font-bold text-stone-900 dark:text-white tracking-tight">{html.escape(self.title)}</a></div><div class="hidden md:flex items-center space-x-2">{desktop_links}</div><div class="hidden md:flex items-center gap-4">{github_button}<button class="theme-toggle-btn p-2 rounded-md text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700">🌙</button></div><div class="-mr-2 flex md:hidden"><button class="theme-toggle-btn p-2 rounded-md text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700">🌙</button><button type="button" id="mobile-menu-button" class="bg-stone-100 dark:bg-stone-800 inline-flex items-center justify-center p-2 rounded-md text-stone-600 dark:text-stone-400 hover:text-stone-800 hover:bg-stone-200 focus:outline-none"><svg class="h-6 w-6 block" id="menu-open-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" /></svg><svg class="h-6 w-6 hidden" id="menu-close-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg></button></div></nav></div><div class="md:hidden hidden" id="mobile-menu"><div class="px-2 pt-2 pb-3 space-y-1 sm:px-3">{mobile_links}</div></div></header>"""

    def _render_footer(self, ack_section: dict[str, Any] | None) -> str:
        """Render the footer section."""
        content = ""
        if ack_section:
            content = ack_section["content_html"]
        return f"""<footer id="acknowledgements" class="bg-stone-800 text-stone-300 dark:bg-black"><div class="container mx-auto py-12 px-4 sm:px-6 lg:px-8 text-center">{f'<h3 class="text-xl font-bold text-white">{html.escape(ack_section["title"])}</h3>' if ack_section else ""}<div class="mt-4 prose-styles max-w-2xl mx-auto">{content}</div><div class="mt-8"><p>&copy; 2025 {html.escape(self.title)}. All Rights Reserved.</p><p class="text-sm text-stone-400">Generated from README.md.</p></div></div></footer>"""

    def _get_javascript(self) -> str:
        """Get JavaScript for interactive features."""
        return """
        // Dark mode toggle
        const themeToggleButtons = document.querySelectorAll('.theme-toggle-btn');
        const html = document.documentElement;

        // Check for saved theme preference or default to system
        const savedTheme = localStorage.getItem('theme');
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        const currentTheme = savedTheme || systemTheme;

        if (currentTheme === 'dark') {
            html.classList.add('dark');
        }

        themeToggleButtons.forEach(button => {
            button.addEventListener('click', () => {
                html.classList.toggle('dark');
                const isDark = html.classList.contains('dark');
                localStorage.setItem('theme', isDark ? 'dark' : 'light');
            });
        });

        // Mobile menu toggle
        const mobileMenuButton = document.getElementById('mobile-menu-button');
        const mobileMenu = document.getElementById('mobile-menu');
        const menuOpenIcon = document.getElementById('menu-open-icon');
        const menuCloseIcon = document.getElementById('menu-close-icon');

        if (mobileMenuButton) {
            mobileMenuButton.addEventListener('click', () => {
                const isOpen = !mobileMenu.classList.contains('hidden');
                mobileMenu.classList.toggle('hidden');
                menuOpenIcon.classList.toggle('hidden');
                menuCloseIcon.classList.toggle('hidden');
            });
        }

        // Smooth scrolling for anchor links
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });

        // Copy button functionality for code blocks
        document.querySelectorAll('pre').forEach(pre => {
            const code = pre.querySelector('code');
            if (code) {
                pre.classList.add('code-block');
                const copyButton = document.createElement('button');
                copyButton.textContent = 'Copy';
                copyButton.className = 'copy-button';
                copyButton.addEventListener('click', () => {
                    navigator.clipboard.writeText(code.textContent).then(() => {
                        copyButton.textContent = 'Copied!';
                        setTimeout(() => {
                            copyButton.textContent = 'Copy';
                        }, 2000);
                    });
                });
                pre.appendChild(copyButton);
            }
        });
        """
