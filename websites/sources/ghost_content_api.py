"""Ghost Content API source adapter.

Talks to a Ghost site's public Content API (https://ghost.org/docs/content-api/)
to discover the site and pull its posts. Requires a Content API key, which the
user supplies after discovery (Ghost never exposes it publicly).
"""
import logging
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from websites.sources.base import (
    REQUEST_TIMEOUT,
    ContentSourceAdapter,
    SourceImage,
    SourcePost,
)

logger = logging.getLogger("postflow")

POSTS_PATH = "/ghost/api/content/posts/"
PAGE_LIMIT = 50


class GhostContentAPISource(ContentSourceAdapter):
    """Fetches posts from a Ghost site's Content API."""

    kind = "ghost_content_api"
    priority = 10

    @classmethod
    def discover(cls, base_url: str, session: requests.Session) -> Optional[dict]:
        url = f"{base_url.rstrip('/')}{POSTS_PATH}"
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
        except Exception:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        if isinstance(payload, dict) and "errors" in payload:
            return {}
        return None

    def fetch_posts(self) -> Iterator[SourcePost]:
        api_key = self.config.get("api_key")
        if not api_key:
            raise ValueError("Ghost Content API key not configured")

        url = f"{self.base_url}{POSTS_PATH}"
        page = 1

        while True:
            response = self.session.get(
                url,
                params={
                    "key": api_key,
                    "include": "tags,authors",
                    "formats": "html",
                    "limit": PAGE_LIMIT,
                    "page": page,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()

            posts = payload.get("posts", [])
            for post in posts:
                try:
                    source_post = self._build_post(post)
                except Exception:
                    logger.exception(
                        "Skipping malformed Ghost post (id=%s)", post.get("id")
                    )
                    continue
                if source_post is not None:
                    yield source_post

            pagination = payload.get("meta", {}).get("pagination", {})
            total_pages = pagination.get("pages", page)
            current_page = pagination.get("page", page)
            if current_page >= total_pages:
                break
            page = current_page + 1

    def _build_post(self, post: dict) -> SourcePost:
        post_url = post["url"]
        published_at = None
        raw_published_at = post.get("published_at")
        if raw_published_at:
            published_at = datetime.fromisoformat(raw_published_at)

        source_post = SourcePost(
            guid=post["id"],
            url=post_url,
            title=post.get("title", ""),
            slug=post.get("slug", ""),
            excerpt=post.get("custom_excerpt") or post.get("excerpt") or "",
            html_body=post.get("html") or "",
            tags=[t["name"] for t in post.get("tags", []) if t.get("name")],
            published_at=published_at,
            images=self._extract_images(post, post_url),
        )
        return source_post

    def _extract_images(self, post: dict, post_url: str) -> list:
        images = []
        seen_urls = set()

        feature_image = post.get("feature_image")
        if feature_image and not feature_image.startswith("data:"):
            resolved = urljoin(post_url, feature_image)
            images.append(
                SourceImage(
                    url=resolved,
                    alt_text=post.get("feature_image_alt") or "",
                    is_feature=True,
                )
            )
            seen_urls.add(resolved)

        html_body = post.get("html") or ""
        if html_body:
            soup = BeautifulSoup(html_body, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src")
                if not src or src.startswith("data:"):
                    continue
                resolved = urljoin(post_url, src)
                if resolved in seen_urls:
                    continue
                seen_urls.add(resolved)
                images.append(SourceImage(url=resolved, alt_text=img.get("alt") or ""))

        return images
