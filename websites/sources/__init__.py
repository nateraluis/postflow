"""Content source adapter registry and site detection."""
import logging

from .base import ContentSourceAdapter, SourceImage, SourcePost, make_session  # noqa: F401

logger = logging.getLogger("postflow")


def _adapters():
    """Import adapters lazily to avoid import cycles; ordered by fidelity."""
    from .ghost_content_api import GhostContentAPISource
    from .ghost_geo import GhostGEOSource
    from .rss import RSSSource
    from .sitemap_crawl import SitemapCrawlSource

    return [GhostContentAPISource, GhostGEOSource, RSSSource, SitemapCrawlSource]


def get_adapter_class(kind: str):
    for cls in _adapters():
        if cls.kind == kind:
            return cls
    raise ValueError(f"Unknown content source kind: {kind}")


def build_adapter(content_source, session=None) -> ContentSourceAdapter:
    """Instantiate the adapter for a websites.models.ContentSource row."""
    cls = get_adapter_class(content_source.kind)
    return cls(content_source.website.url, content_source.config, session=session)


def detect_sources(base_url: str) -> list:
    """Probe a site and return [(kind, config, priority), ...] for every
    supported source, best fidelity first. Never raises."""
    session = make_session()
    found = []
    for cls in _adapters():
        try:
            config = cls.discover(base_url, session)
        except Exception:
            logger.exception(f"Source discovery failed for {cls.kind} on {base_url}")
            config = None
        if config is not None:
            found.append((cls.kind, config, cls.priority))
    return found
