"""
Management command to send weekly digest emails to all users.
Usage: uv run manage.py send_weekly_digest
"""
from django.core.management.base import BaseCommand
from postflow.digest import send_all_digests


class Command(BaseCommand):
    help = "Send weekly digest emails to all active users with connected accounts"

    def handle(self, *args, **options):
        sent, skipped = send_all_digests()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} digests, skipped {skipped}"))
