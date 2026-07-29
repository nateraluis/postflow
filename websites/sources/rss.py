"""RSS/Atom feed source adapter.

Discovers a site's RSS or Atom feed (via a `<link rel="alternate">` tag or by
probing common feed paths) and parses entries with the stdlib
`xml.etree.ElementTree`, matching the parsing conventions already used by
`postflow.management.commands.poll_rss_feeds`, but pulling richer fields
(full HTML body, tags, media images) needed to build a normalized
`SourcePost`.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterator, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from websites.sources.base import (
    REQUEST_TIMEOUT,
    ContentSourceAdapter,
    SourceImage,
    SourcePost,
)

logger = logging.getLogger("postflow")

ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
MEDIA_NS = "http://search.yahoo.com/mrss/"

CANDIDATE_FEED_PATHS = ["/rss/", "/feed/", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml"]

EXCERPT_LIMIT = 300

_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")


def _looks_like_html(text: str) -> bool:
    return bool(text) and bool(_HTML_TAG_RE.search(text))


def _strip_html(text: str, limit: int = EXCERPT_LIMIT) -> str:
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        stripped = soup.get_text(separator=" ", strip=True)
    except Exception:
        stripped = text
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if len(stripped) > limit:
        stripped = stripped[:limit].rstrip()
    return stripped


def _parse_rss_date(value: Optional[str]):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_atom_date(value: Optional[str]):
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _root_tag(root) -> str:
    return root.tag.split("}")[-1].lower()


def _is_feed_xml(content: bytes) -> bool:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return False
    return _root_tag(root) in ("rss", "feed")


class RSSSource(ContentSourceAdapter):
    """Fetches posts from a site's RSS 2.0 or Atom feed."""

    kind = "rss"
    priority = 30

    @classmethod
    def discover(cls, base_url: str, session) -> Optional[dict]:
        base_url = base_url.rstrip("/")

        try:
            response = session.get(base_url, timeout=REQUEST_TIMEOUT)
            if response.ok:
                soup = BeautifulSoup(response.text, "html.parser")
                page_url = response.url or base_url
                for link in soup.find_all("link"):
                    rel = link.get("rel") or []
                    if isinstance(rel, str):
                        rel = [rel]
                    if "alternate" not in [r.lower() for r in rel]:
                        continue
                    link_type = (link.get("type") or "").lower()
                    if link_type not in ("application/rss+xml", "application/atom+xml"):
                        continue
                    href = link.get("href")
                    if href:
                        return {"feed_url": urljoin(page_url, href)}
        except Exception:
            logger.debug("RSS discovery: failed to fetch/parse %s", base_url, exc_info=True)

        for path in CANDIDATE_FEED_PATHS:
            candidate_url = f"{base_url}{path}"
            try:
                response = session.get(candidate_url, timeout=REQUEST_TIMEOUT)
            except Exception:
                continue
            if response.status_code != 200:
                continue
            if _is_feed_xml(response.content):
                return {"feed_url": response.url or candidate_url}

        return None

    def fetch_posts(self) -> Iterator[SourcePost]:
        feed_url = self.config.get("feed_url")
        if not feed_url:
            discovered = self.discover(self.base_url, self.session)
            feed_url = discovered.get("feed_url") if discovered else None
        if not feed_url:
            logger.warning("RSSSource: no feed_url configured or discoverable for %s", self.base_url)
            return

        response = self.session.get(feed_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            logger.exception("RSSSource: failed to parse feed XML at %s", feed_url)
            return

        if _root_tag(root) == "feed":
            yield from self._fetch_atom_entries(root, feed_url)
        else:
            yield from self._fetch_rss_items(root, feed_url)

    # -- RSS 2.0 -----------------------------------------------------

    def _fetch_rss_items(self, root, feed_url: str) -> Iterator[SourcePost]:
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(".//item")
        for item in items:
            try:
                post = self._build_rss_post(item, feed_url)
            except Exception:
                logger.exception("RSSSource: skipping malformed RSS item in feed %s", feed_url)
                continue
            if post is not None:
                yield post

    def _build_rss_post(self, item, feed_url: str) -> Optional[SourcePost]:
        link = (item.findtext("link") or "").strip()
        guid_el = item.find("guid")
        guid = (guid_el.text or "").strip() if guid_el is not None and guid_el.text else ""
        guid = guid or link
        if not guid:
            return None
        entry_url = link or guid

        title = (item.findtext("title") or "").strip()

        description_raw = item.findtext("description") or ""
        content_encoded_el = item.find(f"{{{CONTENT_NS}}}encoded")
        content_encoded = (content_encoded_el.text or "").strip() if content_encoded_el is not None else ""

        html_body = content_encoded
        if not html_body and _looks_like_html(description_raw):
            html_body = description_raw.strip()

        excerpt = _strip_html(description_raw) or _strip_html(html_body)

        tags = [
            (c.text or "").strip()
            for c in item.findall("category")
            if c.text and c.text.strip()
        ]

        published_at = _parse_rss_date(item.findtext("pubDate"))

        images = self._extract_images(item, html_body, entry_url)

        return SourcePost(
            guid=guid,
            url=entry_url,
            title=title,
            excerpt=excerpt,
            html_body=html_body,
            tags=tags,
            published_at=published_at,
            images=images,
        )

    # -- Atom ----------------------------------------------------------

    def _fetch_atom_entries(self, root, feed_url: str) -> Iterator[SourcePost]:
        entries = root.findall(f"{{{ATOM_NS}}}entry")
        for entry in entries:
            try:
                post = self._build_atom_post(entry, feed_url)
            except Exception:
                logger.exception("RSSSource: skipping malformed Atom entry in feed %s", feed_url)
                continue
            if post is not None:
                yield post

    def _build_atom_post(self, entry, feed_url: str) -> Optional[SourcePost]:
        link_el = entry.find(f"{{{ATOM_NS}}}link[@rel='alternate']")
        if link_el is None:
            link_el = entry.find(f"{{{ATOM_NS}}}link")
        href = link_el.get("href") if link_el is not None else ""
        link = urljoin(feed_url, href) if href else ""

        guid = (entry.findtext(f"{{{ATOM_NS}}}id") or "").strip() or link
        if not guid:
            return None
        entry_url = link or guid

        title = (entry.findtext(f"{{{ATOM_NS}}}title") or "").strip()

        summary = entry.findtext(f"{{{ATOM_NS}}}summary") or ""
        content_el = entry.find(f"{{{ATOM_NS}}}content")
        content_text = ""
        if content_el is not None:
            content_text = (content_el.text or "").strip()
            if not content_text and len(content_el):
                # xhtml-typed content nests child elements instead of escaped text.
                try:
                    content_text = "".join(
                        ET.tostring(child, encoding="unicode") for child in content_el
                    ).strip()
                except Exception:
                    content_text = ""

        html_body = content_text
        if not html_body and _looks_like_html(summary):
            html_body = summary.strip()

        excerpt = _strip_html(summary) or _strip_html(html_body)

        tags = [
            (c.get("term") or "").strip()
            for c in entry.findall(f"{{{ATOM_NS}}}category")
            if c.get("term")
        ]

        published_raw = entry.findtext(f"{{{ATOM_NS}}}published") or entry.findtext(f"{{{ATOM_NS}}}updated")
        published_at = _parse_atom_date(published_raw)

        images = self._extract_images(entry, html_body, entry_url)

        return SourcePost(
            guid=guid,
            url=entry_url,
            title=title,
            excerpt=excerpt,
            html_body=html_body,
            tags=tags,
            published_at=published_at,
            images=images,
        )

    # -- Shared ----------------------------------------------------------

    def _extract_images(self, element, html_body: str, entry_url: str) -> list:
        images = []
        seen_urls = set()

        def _add(raw_url, alt_text=""):
            if not raw_url or raw_url.startswith("data:"):
                return
            resolved = urljoin(entry_url, raw_url)
            if resolved.startswith("data:") or resolved in seen_urls:
                return
            seen_urls.add(resolved)
            images.append(SourceImage(url=resolved, alt_text=alt_text))

        for tag in ("content", "thumbnail"):
            for el in element.findall(f"{{{MEDIA_NS}}}{tag}"):
                medium = (el.get("medium") or "").lower()
                media_type = (el.get("type") or "").lower()
                if tag == "content" and medium and medium != "image" and not media_type.startswith("image/"):
                    continue
                _add(el.get("url"))

        for el in element.findall("enclosure"):
            if (el.get("type") or "").lower().startswith("image/"):
                _add(el.get("url"))

        for el in element.findall(f"{{{ATOM_NS}}}link"):
            if el.get("rel") == "enclosure" and (el.get("type") or "").lower().startswith("image/"):
                _add(el.get("href"))

        if html_body:
            try:
                soup = BeautifulSoup(html_body, "html.parser")
                for img in soup.find_all("img"):
                    _add(img.get("src"), img.get("alt") or "")
            except Exception:
                logger.debug("RSSSource: failed to extract <img> tags from body for %s", entry_url, exc_info=True)

        if images:
            images[0].is_feature = True

        return images
