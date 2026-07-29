"""Run the campaign autopilot: plan the coming week and generate drafts.

Usage:
    uv run manage.py run_campaign_autopilot            # all users with websites
    uv run manage.py run_campaign_autopilot --user-id 1
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from campaigns.autopilot import run_autopilot


class Command(BaseCommand):
    help = "Plan the coming week and generate campaign drafts for review"

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int)

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(websites__isnull=False).distinct()
        if options.get("user_id"):
            users = users.filter(id=options["user_id"])

        for user in users:
            try:
                summary, results = run_autopilot(user)
                self.stdout.write(self.style.SUCCESS(
                    f"{user.email}: {len(results)} draft(s) planned. {summary}"
                ))
            except ValueError as e:
                self.stdout.write(f"{user.email}: skipped ({e})")
            except Exception as e:
                self.stderr.write(f"{user.email}: autopilot failed: {e}")
