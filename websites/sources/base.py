"""Common interface for website content source adapters.

An adapter knows how to (a) detect whether a site supports it and
(b) fetch the site's posts in a normalized shape. Adapters never touch the
database; websites/sync.py handles persistence and image downloads.
"""
import ipaddress
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "PostFlow/1.0 (+https://postflow.photo)"
REQUEST_TIMEOUT = 20
MAX_REDIRECTS = 5


class UnsafeURLError(requests.RequestException):
    """URL points at a non-public address (SSRF guard)."""


def validate_public_url(url: str):
    """Reject URLs that don't resolve to public internet addresses.

    Everything this app fetches is user-controlled (site URLs, feed URLs,
    image srcs scraped from fetched pages), so every request must be barred
    from loopback, private, link-local (cloud metadata) and reserved ranges.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"Cannot resolve host {host!r}") from e
    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            raise UnsafeURLError(f"Host {host!r} resolves to non-public address {ip}")


class SafeSession(requests.Session):
    """Session that validates every URL (including each redirect hop) against
    non-public addresses before connecting."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        follow = kwargs.pop("allow_redirects", True)
        hops = 0
        while True:
            validate_public_url(url)
            resp = super().request(method, url, allow_redirects=False, **kwargs)
            if follow and resp.is_redirect and hops < MAX_REDIRECTS:
                url = urljoin(url, resp.headers["location"])
                # The Location URL already carries the query string; re-sending
                # params/body would duplicate them on every hop.
                kwargs.pop("params", None)
                kwargs.pop("data", None)
                kwargs.pop("json", None)
                if resp.status_code in (301, 302, 303) and method.upper() != "GET":
                    method = "GET"
                hops += 1
                continue
            return resp


def make_session() -> requests.Session:
    session = SafeSession()
    session.headers["User-Agent"] = USER_AGENT
    return session


@dataclass
class SourceImage:
    url: str
    alt_text: str = ""
    is_feature: bool = False


@dataclass
class SourcePost:
    guid: str
    url: str
    title: str
    slug: str = ""
    excerpt: str = ""
    html_body: str = ""
    markdown_body: str = ""
    tags: list = field(default_factory=list)
    published_at: Optional[datetime] = None
    images: list = field(default_factory=list)  # list[SourceImage]


class ContentSourceAdapter(ABC):
    """Base class for content source adapters.

    Class attributes:
        kind: matches ContentSource.kind choices.
        priority: default priority when auto-detected (lower = higher fidelity).
    """

    kind: str = ""
    priority: int = 100

    def __init__(self, base_url: str, config: dict, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self.session = session or make_session()

    @classmethod
    @abstractmethod
    def discover(cls, base_url: str, session: requests.Session) -> Optional[dict]:
        """Return a config dict if the site supports this source, else None.

        Must be cheap (a couple of HTTP requests at most) and never raise on
        connection/HTTP errors — return None instead.
        """

    @abstractmethod
    def fetch_posts(self) -> Iterator[SourcePost]:
        """Yield the site's posts, newest first. May raise on hard errors."""
