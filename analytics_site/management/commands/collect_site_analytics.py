from django.core.management.base import BaseCommand

from analytics_site.collect import collect_website
from websites.models import Website


class Command(BaseCommand):
    help = "Collect analytics (Plausible/GSC/Ghost) for websites with active connections."

    def add_arguments(self, parser):
        parser.add_argument(
            "--website", type=int, default=None,
            help="Only collect for this website id (default: all websites with an active connection).",
        )

    def handle(self, *args, **options):
        websites = Website.objects.filter(analytics_connections__is_active=True).distinct()
        website_id = options.get("website")
        if website_id:
            websites = websites.filter(id=website_id)

        if not websites.exists():
            self.stdout.write(self.style.WARNING("No websites with active analytics connections found."))
            return

        for website in websites:
            snapshot, results = collect_website(website)
            summary = ", ".join(f"{provider}: {status}" for provider, status in results.items()) or "no connections"
            ok = all(status == "ok" for status in results.values())
            style = self.style.SUCCESS if ok else self.style.WARNING
            self.stdout.write(style(f"{website} [{snapshot.date}] — {summary}"))
