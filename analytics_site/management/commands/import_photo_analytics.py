"""One-time history import from Tyn-Studio/photo-analytics's SQLite export.

Fetches (or reads locally) the `data/analytics.db` snapshots table produced
by photo-analytics/site-report.py and backfills SiteSnapshot rows so the
dashboard has history predating this app's own collection.

Blob paths mirror photo-analytics/CLAUDE.md:
  - plausible.aggregate.metrics = [visitors, pageviews, bounce_rate, visit_duration, visits]
  - ghost.growth.summary.total_members
"""
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from analytics_site.models import SiteSnapshot
from websites.models import Website

GITHUB_CONTENTS_URL = "https://api.github.com/repos/{repo}/contents/data/analytics.db"
TIMEOUT = 60


class Command(BaseCommand):
    help = "One-time import of historical snapshots from the photo-analytics SQLite database."

    def add_arguments(self, parser):
        parser.add_argument("--website", type=int, required=True, help="Website id to import into.")
        parser.add_argument(
            "--file", type=str, default=None,
            help="Path to a local analytics.db instead of fetching from GitHub.",
        )

    def handle(self, *args, **options):
        try:
            website = Website.objects.get(id=options["website"])
        except Website.DoesNotExist:
            raise CommandError(f"No website with id={options['website']}")

        if options.get("file"):
            db_path = Path(options["file"])
            if not db_path.exists():
                raise CommandError(f"File not found: {db_path}")
            imported = self._import_from_path(website, db_path)
        else:
            db_bytes = self._fetch_from_github()
            with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
                tmp.write(db_bytes)
                tmp.flush()
                imported = self._import_from_path(website, Path(tmp.name))

        self.stdout.write(self.style.SUCCESS(f"Imported/updated {imported} snapshot(s) for {website}."))
        self._recompute_subscriber_deltas(website)

    def _fetch_from_github(self) -> bytes:
        if not settings.GITHUB_ANALYTICS_TOKEN:
            raise CommandError("GITHUB_ANALYTICS_TOKEN is not set; pass --file instead.")
        url = GITHUB_CONTENTS_URL.format(repo=settings.PHOTO_ANALYTICS_REPO)
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {settings.GITHUB_ANALYTICS_TOKEN}",
                "Accept": "application/vnd.github.raw+json",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.content

    def _import_from_path(self, website, db_path: Path) -> int:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT date, days, ghost, plausible, gsc, suggest FROM snapshots ORDER BY date ASC"
            ).fetchall()
        finally:
            conn.close()

        count = 0
        for row in rows:
            try:
                date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue

            ghost = json.loads(row["ghost"]) if row["ghost"] else {}
            plausible = json.loads(row["plausible"]) if row["plausible"] else {}
            gsc = json.loads(row["gsc"]) if row["gsc"] else {}
            suggest = json.loads(row["suggest"]) if row["suggest"] else {}

            snapshot, _ = SiteSnapshot.objects.update_or_create(
                website=website,
                date=date,
                defaults={
                    "days": row["days"] or 1,
                    "ghost": ghost,
                    "plausible": plausible,
                    "gsc": gsc,
                    "suggest": suggest,
                },
            )

            metrics = plausible.get("aggregate", {}).get("metrics") or []
            snapshot.visitors = metrics[0] if len(metrics) > 0 else None
            snapshot.pageviews = metrics[1] if len(metrics) > 1 else None
            snapshot.subscribers = ghost.get("growth", {}).get("summary", {}).get("total_members")
            snapshot.save(update_fields=["visitors", "pageviews", "subscribers"])
            count += 1

        return count

    def _recompute_subscriber_deltas(self, website):
        """subscriber_delta depends on the previous row's subscribers, so it's
        computed in a second pass once all rows for this import are in place."""
        snapshots = list(
            SiteSnapshot.objects.filter(website=website).order_by("date")
        )
        previous_subscribers = None
        to_update = []
        for snapshot in snapshots:
            if snapshot.subscribers is not None and previous_subscribers is not None:
                delta = snapshot.subscribers - previous_subscribers
                if snapshot.subscriber_delta != delta:
                    snapshot.subscriber_delta = delta
                    to_update.append(snapshot)
            if snapshot.subscribers is not None:
                previous_subscribers = snapshot.subscribers

        if to_update:
            SiteSnapshot.objects.bulk_update(to_update, ["subscriber_delta"])
