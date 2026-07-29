"""Sync content from connected websites.

Usage:
    uv run manage.py sync_website_content            # all websites
    uv run manage.py sync_website_content --website 3
"""
import logging

from django.core.management.base import BaseCommand

from websites.models import Website
from websites.sync import sync_website

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = "Sync content (posts + images) from connected websites"

    def add_arguments(self, parser):
        parser.add_argument("--website", type=int, help="Sync only this website id")

    def handle(self, *args, **options):
        websites = Website.objects.all()
        if options.get("website"):
            websites = websites.filter(id=options["website"])

        total_created = total_updated = failures = 0
        for website in websites:
            try:
                created, updated = sync_website(website)
                total_created += created
                total_updated += updated
            except Exception as e:
                failures += 1
                self.stderr.write(f"Sync failed for {website.url}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Website sync done: {total_created} created, {total_updated} updated, "
            f"{failures} site(s) failed"
        ))
