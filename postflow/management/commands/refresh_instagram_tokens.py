# management/commands/refresh_instagram_tokens.py
from django.core.management.base import BaseCommand
from postflow.models import InstagramBusinessAccount
from postflow.utils.instagram import refresh_long_lived_token

class Command(BaseCommand):
    help = "Refresh Instagram long-lived tokens"

    def handle(self, *args, **options):
        for account in InstagramBusinessAccount.objects.all():
            if account.is_token_expiring(days=7):
                success = refresh_long_lived_token(account)
                if success:
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ Refreshed token for {account.username}"
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Failed to refresh token for {account.username}"
                    ))
