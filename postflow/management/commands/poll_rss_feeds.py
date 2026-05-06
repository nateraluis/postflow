"""
Management command to poll RSS feeds and create scheduled posts from new entries.
Usage: uv run manage.py poll_rss_feeds
"""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from postflow.models import RSSFeed, ScheduledPost

logger = logging.getLogger("postflow")


def parse_feed(url):
    """Parse RSS/Atom feed and return list of entries."""
    resp = requests.get(url, timeout=15, headers={"User-Agent": "PostFlow/1.0"})
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    entries = []

    # RSS 2.0
    for item in root.findall(".//item"):
        entries.append({
            "title": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "summary": (item.findtext("description") or "")[:300].strip(),
            "author": (item.findtext("author") or item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip(),
            "guid": (item.findtext("guid") or item.findtext("link") or "").strip(),
        })

    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        entries.append({
            "title": (entry.findtext("atom:title", namespaces=ns) or "").strip(),
            "url": link.strip(),
            "summary": (entry.findtext("atom:summary", namespaces=ns) or entry.findtext("atom:content", namespaces=ns) or "")[:300].strip(),
            "author": (entry.findtext("atom:author/atom:name", namespaces=ns) or "").strip(),
            "guid": (entry.findtext("atom:id", namespaces=ns) or link or "").strip(),
        })

    return entries


class Command(BaseCommand):
    help = "Poll active RSS feeds and create scheduled posts from new entries"

    def handle(self, *args, **options):
        feeds = RSSFeed.objects.filter(is_active=True)
        created = 0

        for feed in feeds:
            try:
                entries = parse_feed(feed.url)
                if not entries:
                    continue

                # Find new entries (after last processed GUID)
                new_entries = []
                if feed.last_entry_guid:
                    for entry in entries:
                        if entry["guid"] == feed.last_entry_guid:
                            break
                        new_entries.append(entry)
                else:
                    # First poll: only take the latest entry
                    new_entries = entries[:1]

                for entry in reversed(new_entries):  # Oldest first
                    caption = feed.caption_template.format(
                        title=entry["title"],
                        url=entry["url"],
                        summary=entry["summary"],
                        author=entry["author"],
                    )

                    post = ScheduledPost.objects.create(
                        user=feed.user,
                        caption=caption,
                        post_date=timezone.now(),
                        status="pending",
                    )
                    post.mastodon_accounts.set(feed.mastodon_accounts.all())
                    post.mastodon_native_accounts.set(feed.mastodon_native_accounts.all())
                    if feed.include_instagram:
                        post.instagram_accounts.set(feed.instagram_accounts.all())

                    created += 1
                    logger.info(f"Created post from RSS entry: {entry['title']}")

                # Update last processed entry
                if entries:
                    feed.last_entry_guid = entries[0]["guid"]
                feed.last_checked_at = timezone.now()
                feed.save(update_fields=["last_entry_guid", "last_checked_at"])

            except Exception as e:
                logger.error(f"Error polling feed '{feed.name}' ({feed.url}): {e}")

        self.stdout.write(self.style.SUCCESS(f"Created {created} posts from RSS feeds"))
