"""Generate the weekly AI campaign report.

Usage:
    uv run manage.py generate_campaign_report            # all users with websites
    uv run manage.py generate_campaign_report --user-id 1
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from campaigns.evaluator import generate_report


class Command(BaseCommand):
    help = "Generate the weekly campaign evaluation report(s)"

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int)

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(websites__isnull=False).distinct()
        if options.get("user_id"):
            users = users.filter(id=options["user_id"])

        for user in users:
            try:
                report = generate_report(user)
                self.stdout.write(self.style.SUCCESS(
                    f"Report for {user.email}, week of {report.week_start} "
                    f"({report.input_tokens}+{report.output_tokens} tokens)"
                ))
            except Exception as e:
                self.stderr.write(f"Report failed for {user.email}: {e}")
