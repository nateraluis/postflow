"""Persist content fetched by source adapters: upsert BlogPosts and download images."""
import logging
import os
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.utils import timezone

from .models import BlogPost, BlogPostImage
from .sources import build_adapter, make_session

logger = logging.getLogger("postflow")

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_POSTS_PER_SYNC = 500


class SyncError(Exception):
    pass


def sync_website(website):
    """Sync a website's content from its best active source.

    Returns (created, updated) counts. Sets sync_status/sync_error on the website.
    """
    source = website.best_source
    if source is None:
        website.sync_status = "error"
        website.sync_error = "No active content source configured."
        website.save(update_fields=["sync_status", "sync_error"])
        raise SyncError(website.sync_error)

    website.sync_status = "syncing"
    website.sync_error = ""
    website.save(update_fields=["sync_status", "sync_error"])

    session = make_session()
    enrich_markdown = _geo_enricher(website, source, session)
    created = updated = 0

    try:
        adapter = build_adapter(source, session=session)
        for count, source_post in enumerate(adapter.fetch_posts()):
            if count >= MAX_POSTS_PER_SYNC:
                logger.warning(f"Post cap reached for {website.url}; stopping sync")
                break
            try:
                was_created = _upsert_post(website, source_post, enrich_markdown, session)
                created += was_created
                updated += not was_created
            except Exception:
                logger.exception(
                    f"Failed to sync post {source_post.url} for {website.url}"
                )
    except Exception as e:
        website.sync_status = "error"
        website.sync_error = str(e)[:2000]
        website.save(update_fields=["sync_status", "sync_error"])
        raise

    website.sync_status = "ok"
    website.last_synced_at = timezone.now()
    website.save(update_fields=["sync_status", "last_synced_at"])
    logger.info(f"Synced {website.url}: {created} created, {updated} updated")
    return created, updated


def _geo_enricher(website, primary_source, session):
    """If the site supports Ghost GEO and the primary source doesn't yield
    markdown, return a callable that fetches a post's .md body. Else None."""
    if primary_source.kind == "ghost_geo":
        return None
    if not website.sources.filter(kind="ghost_geo", is_active=True).exists():
        return None

    from .sources.ghost_geo import fetch_markdown

    return lambda url: fetch_markdown(url, session)


def _url_variants(url):
    """Trailing-slash and scheme variants of a URL, for cross-source matching."""
    out = {url}
    stripped = url.rstrip("/")
    out.update({stripped, stripped + "/"})
    for u in list(out):
        if u.startswith("https://"):
            out.add("http://" + u[8:])
        elif u.startswith("http://"):
            out.add("https://" + u[7:])
    return [u for u in out if u]


def _upsert_post(website, sp, enrich_markdown, session):
    """Create or update one BlogPost from a SourcePost. Returns True if created."""
    post = BlogPost.objects.filter(website=website, source_guid=sp.guid).first()
    created = False
    if post is None and sp.url:
        # Each adapter keys posts differently (Ghost id, canonical URL, feed
        # guid). When the site's best source changes, match the existing row
        # by URL and adopt the new guid rather than duplicating the catalog.
        post = BlogPost.objects.filter(
            website=website, url__in=_url_variants(sp.url)
        ).first()
        if post is not None:
            post.source_guid = sp.guid
            post.save(update_fields=["source_guid"])
    if post is None:
        post = BlogPost.objects.create(
            website=website,
            source_guid=sp.guid,
            title=sp.title[:500],
            url=sp.url,
        )
        created = True

    # Never overwrite good data with empty values from a lower-fidelity fetch
    fields = {
        "title": sp.title[:500],
        "slug": sp.slug[:500],
        "url": sp.url,
        "excerpt": sp.excerpt,
        "html_body": sp.html_body,
        "markdown_body": sp.markdown_body,
        "tags": sp.tags,
        "published_at": sp.published_at,
    }
    changed = []
    for name, value in fields.items():
        if value and getattr(post, name) != value:
            setattr(post, name, value)
            changed.append(name)

    if not post.markdown_body and enrich_markdown is not None:
        markdown = enrich_markdown(post.url)
        if markdown:
            post.markdown_body = markdown
            changed.append("markdown_body")

    if changed:
        post.save(update_fields=changed + ["updated_at"])

    _sync_images(post, sp.images, session)
    return created


def _sync_images(post, source_images, session):
    for order, si in enumerate(source_images):
        if not si.url or len(si.url) > 1000:
            continue
        image, created = BlogPostImage.objects.get_or_create(
            blog_post=post,
            source_url=si.url,
            defaults={
                "alt_text": si.alt_text,
                "is_feature": si.is_feature,
                "order": order,
            },
        )
        if not image.image:
            content = _download_image(si.url, session)
            if content is not None:
                image.image.save(_image_filename(si.url), content, save=True)


def _download_image(url, session):
    try:
        resp = session.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            logger.warning(f"Skipping non-image URL {url} ({content_type})")
            return None
        chunks = []
        size = 0
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                logger.warning(f"Skipping oversized image {url}")
                return None
            chunks.append(chunk)
        return ContentFile(b"".join(chunks))
    except Exception:
        logger.exception(f"Failed to download image {url}")
        return None


def _image_filename(url):
    name = os.path.basename(urlparse(url).path) or "image.jpg"
    if "." not in name:
        name += ".jpg"
    return name[:100]
