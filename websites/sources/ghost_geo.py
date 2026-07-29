"""Ghost GEO (llms.txt) source adapter.

Ghost's built-in "GEO" (Generative Engine Optimization) feature, toggled on
per-site under Settings -> Meta data, publishes two things:

1. `{site}/llms.txt` - a Markdown index of the site's public content, with a
   `## Posts` (and optionally `## Pages`) section listing `[Title](url) -
   description` links.
2. A Markdown rendition of each post/page, served by appending `.md` to the
   post's URL with any trailing slash removed first, e.g.
   `https://example.com/my-post/` -> `https://example.com/my-post.md`.

Verified directly against `https://ghost.org/changelog` (a real Ghost site
with GEO enabled): `https://ghost.org/changelog/geo.md` returns
`200 text/markdown`, while the trailing-slash form
`https://ghost.org/changelog/geo/.md` returns `403`. A site with GEO
*disabled* (or a hand-authored `llms.txt` that isn't Ghost's generated one,
as currently seen on some sites) either 404s or silently redirects the `.md`
URL back to the normal HTML page, so `fetch_markdown` treats a redirect away
from a `.md` path, or an HTML-looking body, as failure.

A real Ghost GEO post's Markdown body looks like:

    > ## Content Index
    > Fetch the complete content index at: https://example.com/llms.txt
    > Use this file to discover other available public pages...

    # Post Title
    - URL: https://example.com/post-slug/
    - Published: 2026-07-16T18:01:16.000Z
    - Updated: 2026-07-16T18:01:16.000Z
    - Description: A short description
    - Author: Jane Doe
    - Tags: Tag One, Tag Two

    First real paragraph of the post body...

which this module leans on for the leading `# ` title fallback, the
`- Published:` frontmatter date, and skipping non-prose lines when picking
an excerpt.
"""
import logging
import re
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

import requests

from websites.sources.base import (
    REQUEST_TIMEOUT,
    ContentSourceAdapter,
    SourceImage,
    SourcePost,
)

logger = logging.getLogger("postflow")

EXCERPT_LIMIT = 300

# A bullet-list link line, e.g. `- [Title](url) - description` or `* [Title](url)`.
_LINK_LINE_RE = re.compile(r"^[-*]\s*\[([^\]]*)\]\(([^)]+)\)")
_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_POSTS_SECTION_RE = re.compile(r"^(posts?|articles?|selected\s+posts?|latest\s+posts?)$", re.IGNORECASE)
_SKIP_SECTION_TITLES = {"links", "contact", "about", "key topics", "pages"}

_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")
_FRONTMATTER_LINE_RE = re.compile(r"^-\s*[A-Za-z][\w ]{0,24}:\s")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_PUBLISHED_LINE_RE = re.compile(r"^-\s*Published:\s*(.+)$", re.IGNORECASE)


def fetch_markdown(post_url: str, session: requests.Session) -> str:
    """Fetch the Markdown rendition of a Ghost post/page URL.

    Tries `{url without trailing slash}.md` first (the verified pattern),
    then a couple of fallback variants, and returns "" if none work. Used
    both by GhostGEOSource.fetch_posts and by other source adapters that
    want to enrich a post discovered elsewhere (e.g. via RSS) with a
    Markdown body.
    """
    if not post_url:
        return ""

    candidates = []
    if post_url.endswith(".md"):
        candidates.append(post_url)
    else:
        stripped = post_url.rstrip("/")
        if stripped:
            candidates.append(f"{stripped}.md")
        if post_url != stripped:
            candidates.append(f"{post_url}.md")

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)

        try:
            response = session.get(
                candidate,
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "text/markdown, text/plain;q=0.9, */*;q=0.8"},
            )
        except Exception:
            logger.debug("ghost_geo: fetch_markdown request failed for %s", candidate, exc_info=True)
            continue

        if response.status_code != 200:
            continue

        # Sites without GEO enabled (or fronted by a CDN that doesn't know
        # the `.md` route) tend to redirect back to the normal HTML page
        # instead of 404ing. If we didn't land on a `.md` URL, this wasn't
        # really Markdown.
        final_url = (response.url or candidate).split("?", 1)[0]
        if not final_url.endswith(".md"):
            continue

        text = response.text or ""
        stripped_text = text.lstrip()
        looks_like_html = stripped_text[:15].lower().startswith(("<!doctype", "<html", "<?xml"))
        if looks_like_html:
            continue

        if not text.strip():
            continue

        return text

    return ""


def _iter_link_lines(text: str):
    """Yield (section_title_lower_or_None, link_text, href) for every bullet link line."""
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading_match = _SECTION_HEADING_RE.match(line)
        if heading_match:
            section = heading_match.group(1).strip().lower()
            continue
        link_match = _LINK_LINE_RE.match(line)
        if not link_match:
            continue
        yield section, link_match.group(1).strip(), link_match.group(2).strip()


def _extract_post_links(text: str):
    """Return an ordered, deduped list of (title, href) post links from llms.txt.

    Prefers links found under a `## Posts` (or similarly named) heading,
    since that's how Ghost's generated llms.txt is structured. Falls back to
    every link in the document that isn't under an obviously non-post
    section (Links, Contact, About, ...) for hand-authored llms.txt files
    that don't follow Ghost's exact section naming.
    """
    all_links = list(_iter_link_lines(text))

    posts_section_links = [
        (title, href) for section, title, href in all_links
        if section is not None and _POSTS_SECTION_RE.match(section)
    ]
    candidates = posts_section_links
    if not candidates:
        candidates = [
            (title, href) for section, title, href in all_links
            if section not in _SKIP_SECTION_TITLES
        ]

    seen = set()
    ordered = []
    for title, href in candidates:
        if not href or href.startswith(("mailto:", "#", "javascript:")):
            continue
        if href in seen:
            continue
        seen.add(href)
        ordered.append((title, href))
    return ordered


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        return ""
    slug = segments[-1]
    if slug.endswith(".md"):
        slug = slug[:-3]
    return slug


def _title_from_slug(url: str) -> str:
    slug = _slug_from_url(url)
    if not slug:
        return url
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _extract_heading(markdown_body: str) -> str:
    """Return the text of a leading `# ` heading, skipping blank/blockquote lines."""
    if not markdown_body:
        return ""
    for line in markdown_body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        match = _HEADING_RE.match(stripped)
        return match.group(1).strip() if match else ""
    return ""


def _extract_excerpt(markdown_body: str, limit: int = EXCERPT_LIMIT) -> str:
    """Return the first real prose paragraph, skipping headings, blockquotes,
    image-only lines, and Ghost's `- Key: value` frontmatter block."""
    if not markdown_body:
        return ""
    paragraphs = re.split(r"\n\s*\n", markdown_body.strip())
    for para in paragraphs:
        lines = [line.strip() for line in para.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith(">") for line in lines):
            continue
        if lines[0].startswith("#"):
            continue
        if lines[0].startswith("!["):
            continue
        if all(_FRONTMATTER_LINE_RE.match(line) for line in lines):
            continue
        text = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if not text:
            continue
        if len(text) > limit:
            truncated = text[:limit].rsplit(" ", 1)[0]
            text = f"{truncated}..."
        return text
    return ""


def _extract_images(markdown_body: str, post_url: str) -> list:
    if not markdown_body:
        return []
    images = []
    seen = set()
    for match in _IMAGE_RE.finditer(markdown_body):
        alt, src = match.group(1).strip(), match.group(2).strip()
        if not src or src.startswith("data:"):
            continue
        resolved = urljoin(post_url, src)
        if resolved.startswith("data:") or resolved in seen:
            continue
        seen.add(resolved)
        images.append(SourceImage(url=resolved, alt_text=alt, is_feature=not images))
    return images


def _extract_published_at(markdown_body: str) -> Optional[datetime]:
    if not markdown_body:
        return None
    for line in markdown_body.splitlines()[:20]:
        match = _PUBLISHED_LINE_RE.match(line.strip())
        if not match:
            continue
        raw = match.group(1).strip()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class GhostGEOSource(ContentSourceAdapter):
    """Fetches posts from a Ghost site's GEO llms.txt index + per-post Markdown."""

    kind = "ghost_geo"
    priority = 20

    @classmethod
    def discover(cls, base_url: str, session: requests.Session) -> Optional[dict]:
        try:
            url = f"{base_url.rstrip('/')}/llms.txt"
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return None
            body = response.text or ""
            if "](" in body:
                return {}
            return None
        except Exception:
            logger.debug("ghost_geo: discovery failed for %s", base_url, exc_info=True)
            return None

    def fetch_posts(self) -> Iterator[SourcePost]:
        index_url = f"{self.base_url}/llms.txt"
        try:
            response = self.session.get(index_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            text = response.text or ""
        except Exception:
            logger.warning("ghost_geo: failed to fetch %s", index_url, exc_info=True)
            return

        base_netloc = urlparse(self.base_url).netloc
        seen_urls = set()

        for title_text, href in _extract_post_links(text):
            try:
                abs_url = urljoin(f"{self.base_url}/", href)
                parsed = urlparse(abs_url)
                if parsed.netloc and base_netloc and parsed.netloc != base_netloc:
                    continue

                canonical_url = abs_url[:-3] if abs_url.endswith(".md") else abs_url
                if canonical_url in seen_urls:
                    continue
                seen_urls.add(canonical_url)

                markdown_body = fetch_markdown(canonical_url, self.session)
                if not markdown_body:
                    logger.warning("ghost_geo: no Markdown body for %s, yielding with empty body", canonical_url)

                title = title_text.strip() or _extract_heading(markdown_body) or _title_from_slug(canonical_url)

                yield SourcePost(
                    guid=canonical_url,
                    url=canonical_url,
                    title=title,
                    slug=_slug_from_url(canonical_url),
                    excerpt=_extract_excerpt(markdown_body),
                    html_body="",
                    markdown_body=markdown_body,
                    tags=[],
                    published_at=_extract_published_at(markdown_body),
                    images=_extract_images(markdown_body, canonical_url),
                )
            except Exception:
                logger.warning("ghost_geo: skipping post link %r (%s)", title_text, href, exc_info=True)
                continue
