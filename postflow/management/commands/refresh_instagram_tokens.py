# management/commands/refresh_instagram_tokens.py
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from postflow.models import InstagramBusinessAccount
from postflow.views import refresh_long_lived_token
import logging

logger = logging.getLogger("postflow")

class Command(BaseCommand):
    help = "Refresh Instagram long-lived tokens expiring within 2 days"

    def handle(self, *args, **options):
        start_time = now()
        self.stdout.write(f"Starting Instagram token refresh at {start_time}")

        # Get all accounts and check expiration status
        all_accounts = InstagramBusinessAccount.objects.all()
        total_accounts = all_accounts.count()
        accounts_checked = 0
        tokens_refreshed = 0
        refresh_failures = 0

        if total_accounts == 0:
            self.stdout.write(self.style.WARNING("⚠️ No Instagram accounts found to check"))
            logger.info("Instagram token refresh: No accounts found")
            return

        self.stdout.write(f"Found {total_accounts} Instagram account(s) to check")
        logger.info(f"Starting Instagram token refresh for {total_accounts} account(s)")

        for account in all_accounts:
            accounts_checked += 1

            # Check if token is expiring within 2 days (reduced from 7 for earlier detection)
            if account.is_token_expiring(days=2):
                self.stdout.write(self.style.WARNING(
                    f"[{accounts_checked}/{total_accounts}] ⚠️ Token for {account.username} expires soon. Refreshing..."
                ))
                logger.warning(f"Token expiring soon for {account.username}, attempting refresh")

                success = refresh_long_lived_token(account)
                if success:
                    self.stdout.write(self.style.SUCCESS(
                        f"[{accounts_checked}/{total_accounts}] ✅ Token refreshed for {account.username}"
                    ))
                    logger.info(f"Token successfully refreshed for {account.username}")
                    tokens_refreshed += 1
                else:
                    self.stdout.write(self.style.ERROR(
                        f"[{accounts_checked}/{total_accounts}] ❌ Failed to refresh token for {account.username}"
                    ))
                    logger.error(f"Token refresh failed for {account.username}")
                    refresh_failures += 1
            else:
                # Token is not expiring soon, log it but don't refresh
                expires_at = account.expires_at
                if expires_at:
                    days_until_expiry = (expires_at - now()).days
                    logger.debug(f"Token for {account.username} valid for {days_until_expiry} more days")

        # Summary report
        end_time = now()
        duration = (end_time - start_time).total_seconds()

        summary = (
            f"\n{'='*60}\n"
            f"Instagram Token Refresh Summary\n"
            f"{'='*60}\n"
            f"Accounts checked: {accounts_checked}\n"
            f"Tokens refreshed: {tokens_refreshed}\n"
            f"Refresh failures: {refresh_failures}\n"
            f"Duration: {duration:.2f}s\n"
            f"{'='*60}"
        )

        self.stdout.write(self.style.SUCCESS(summary))
        logger.info(f"Instagram token refresh complete: checked={accounts_checked}, refreshed={tokens_refreshed}, failed={refresh_failures}")

        # Log warning if there were failures
        if refresh_failures > 0:
            warning_msg = f"⚠️ {refresh_failures} token refresh(es) failed. Check logs for details."
            self.stdout.write(self.style.WARNING(warning_msg))
            logger.warning(warning_msg)
