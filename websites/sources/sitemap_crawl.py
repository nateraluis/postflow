"""Sitemap crawl source adapter.

Lowest-fidelity fallback for sites with no Ghost API, no GEO markup, and no
RSS feed: walk the site's sitemap.xml (or sitemap index) to find article
URLs, then scrape each page's HTML directly for title/excerpt/body/images.
"""
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from websites.sources.base import (
    REQUEST_TIMEOUT,
    ContentSourceAdapter,
    SourceImage,
    SourcePost,
)

logger = logging.getLogger("postflow")

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

MAX_URLS_CONSIDERED = 100
MAX_PAGES_FETCHED = 50
FETCH_DELAY_SECONDS = 0.3

NON_ARTICLE_PATH_SEGMENTS = ("/tag/", "/tags/", "/author/", "/category/", "/page/")
NON_ARTICLE_PATH_PREFIXES = ("/about", "/contact", "/privacy", "/terms")
POST_SITEMAP_HINTS = ("post", "article", "blog")

MIN_IMAGE_DIMENSION = 50


class SitemapCrawlSource(ContentSourceAdapter):
    """Crawls a site's sitemap and scrapes article pages directly."""

    kind = "sitemap_crawl"
    priority = 40

    @classmethod
    def discover(cls, base_url: str, session: requests.Session) -> Optional[dict]:
        base_url = base_url.rstrip("/")
        candidates = []

        try:
            response = session.get(f"{base_url}/robots.txt", timeout=REQUEST_TIMEOUT)
            if response.ok:
                for line in response.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        if sitemap_url:
                            candidates.append(sitemap_url)
        except Exception:
            pass

        candidates.append(f"{base_url}/sitemap.xml")
        candidates.append(f"{base_url}/sitemap_index.xml")

        for url in candidates:
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT)
                if not response.ok:
                    continue
                root = ET.fromstring(response.content)
            except Exception:
                continue

            if root.tag in (f"{SITEMAP_NS}urlset", f"{SITEMAP_NS}sitemapindex"):
                return {"sitemap_url": url}

        return None

    def fetch_posts(self) -> Iterator[SourcePost]:
        sitemap_url = self.config.get("sitemap_url") or f"{self.base_url}/sitemap.xml"
        entries = self._collect_page_entries(sitemap_url)

        fetched = 0
        for url, lastmod in entries:
            if fetched >= MAX_PAGES_FETCHED:
                break
            if fetched > 0:
                time.sleep(FETCH_DELAY_SECONDS)
            fetched += 1

            try:
                post = self._fetch_and_parse_page(url, lastmod)
            except Exception:
                logger.warning(
                    "sitemap_crawl: failed to fetch/parse %s", url, exc_info=True
                )
                continue

            if post is None:
                continue
            yield post

    # -- sitemap parsing -----------------------------------------------

    def _fetch_xml(self, url: str) -> Optional[ET.Element]:
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return ET.fromstring(response.content)
        except Exception:
            logger.warning("sitemap_crawl: failed to fetch/parse sitemap %s", url, exc_info=True)
            return None

    def _collect_page_entries(self, sitemap_url: str) -> list:
        root = self._fetch_xml(sitemap_url)
        if root is None:
            return []

        url_entries = []

        if root.tag == f"{SITEMAP_NS}sitemapindex":
            sub_sitemaps = []
            for sitemap_el in root.findall(f"{SITEMAP_NS}sitemap"):
                loc_el = sitemap_el.find(f"{SITEMAP_NS}loc")
                if loc_el is not None and loc_el.text:
                    sub_sitemaps.append(loc_el.text.strip())

            preferred = [
                u for u in sub_sitemaps
                if any(hint in u.lower() for hint in POST_SITEMAP_HINTS)
            ]
            chosen = preferred if preferred else sub_sitemaps

            for sub_url in chosen:
                sub_root = self._fetch_xml(sub_url)
                if sub_root is None:
                    continue
                url_entries.extend(self._parse_urlset(sub_root))
        elif root.tag == f"{SITEMAP_NS}urlset":
            url_entries.extend(self._parse_urlset(root))

        filtered = [(url, lastmod) for url, lastmod in url_entries if self._looks_like_article(url)]

        with_lastmod = sorted(
            (e for e in filtered if e[1] is not None), key=lambda e: e[1], reverse=True
        )
        without_lastmod = [e for e in filtered if e[1] is None]

        return (with_lastmod + without_lastmod)[:MAX_URLS_CONSIDERED]

    def _parse_urlset(self, root: ET.Element) -> list:
        entries = []
        for url_el in root.findall(f"{SITEMAP_NS}url"):
            loc_el = url_el.find(f"{SITEMAP_NS}loc")
            if loc_el is None or not loc_el.text:
                continue
            loc = loc_el.text.strip()

            lastmod = None
            lastmod_el = url_el.find(f"{SITEMAP_NS}lastmod")
            if lastmod_el is not None and lastmod_el.text:
                lastmod = self._parse_datetime(lastmod_el.text.strip())

            entries.append((loc, lastmod))
        return entries

    def _looks_like_article(self, url: str) -> bool:
        path = urlparse(url).path or "/"
        normalized = path.rstrip("/") or "/"
        if normalized == "/":
            return False

        lowered = normalized.lower()
        haystack = lowered + "/"
        if any(segment in haystack for segment in NON_ARTICLE_PATH_SEGMENTS):
            return False
        if any(
            lowered == prefix or lowered.startswith(prefix + "/") or lowered.startswith(prefix + "-")
            for prefix in NON_ARTICLE_PATH_PREFIXES
        ):
            return False
        return True

    # -- page parsing ----------------------------------------------------

    def _fetch_and_parse_page(self, url: str, lastmod: Optional[datetime]) -> Optional[SourcePost]:
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            return None

        content_root = self._find_content_root(soup)
        html_body = content_root.decode_contents().strip() if content_root is not None else ""

        return SourcePost(
            guid=url,
            url=url,
            title=title,
            slug=self._slug_from_url(url),
            excerpt=self._extract_excerpt(soup),
            html_body=html_body,
            published_at=self._extract_published_at(soup) or lastmod,
            images=self._extract_images(soup, content_root, url),
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return ""

    def _extract_excerpt(self, soup: BeautifulSoup) -> str:
        text = ""
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            text = og_desc["content"].strip()
        else:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                text = meta_desc["content"].strip()

        if len(text) > 300:
            text = text[:300].rsplit(" ", 1)[0].rstrip() + "…"
        return text

    def _find_content_root(self, soup: BeautifulSoup):
        # Prefer <article>, but pages can carry more than one (e.g. search
        # widgets, "related posts" cards) — pick the one with the most
        # paragraph text rather than the first in document order.
        articles = soup.find_all("article")
        best_article, best_article_len = self._most_textful(articles)
        if best_article is not None and best_article_len > 0:
            return best_article

        candidates = []
        main = soup.find("main")
        if main is not None:
            candidates.append(main)
        candidates.extend(soup.find_all("div"))

        best, best_len = self._most_textful(candidates)
        return best

    def _most_textful(self, candidates):
        best = None
        best_len = 0
        for candidate in candidates:
            text_len = sum(len(p.get_text(strip=True)) for p in candidate.find_all("p"))
            if text_len > best_len:
                best_len = text_len
                best = candidate
        return best, best_len

    def _extract_images(self, soup: BeautifulSoup, content_root, page_url: str) -> list:
        images = []
        seen = set()

        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            content = og_image["content"].strip()
            if content and not content.startswith("data:"):
                resolved = urljoin(page_url, content)
                images.append(SourceImage(url=resolved, is_feature=True))
                seen.add(resolved)

        if content_root is not None:
            for img in content_root.find_all("img"):
                src = img.get("src")
                if not src or src.startswith("data:"):
                    continue
                if self._looks_like_tracking_pixel(img):
                    continue
                resolved = urljoin(page_url, src)
                if resolved in seen:
                    continue
                seen.add(resolved)
                images.append(SourceImage(url=resolved, alt_text=img.get("alt") or ""))

        return images

    def _looks_like_tracking_pixel(self, img) -> bool:
        for attr in ("width", "height"):
            value = img.get(attr)
            if value is None:
                continue
            try:
                dimension = float(str(value).strip().rstrip("px"))
            except ValueError:
                continue
            if dimension < MIN_IMAGE_DIMENSION:
                return True
        return False

    def _extract_published_at(self, soup: BeautifulSoup) -> Optional[datetime]:
        meta = soup.find("meta", attrs={"property": "article:published_time"})
        if meta and meta.get("content"):
            parsed = self._parse_datetime(meta["content"].strip())
            if parsed:
                return parsed

        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            parsed = self._parse_datetime(time_el["datetime"].strip())
            if parsed:
                return parsed

        return None

    def _parse_datetime(self, text: str) -> Optional[datetime]:
        text = text.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _slug_from_url(self, url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        if not path:
            return ""
        return path.rsplit("/", 1)[-1]
