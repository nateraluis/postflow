# management/commands/refresh_threads_tokens.py
import logging

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from threads.models import ThreadsAccount
from threads.views import refresh_threads_token

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = "Refresh Threads long-lived tokens expiring within 10 days"

    def handle(self, *args, **options):
        start_time = now()
        self.stdout.write(f"Starting Threads token refresh at {start_time}")

        all_accounts = ThreadsAccount.objects.all()
        total_accounts = all_accounts.count()
        accounts_checked = 0
        tokens_refreshed = 0
        refresh_failures = 0

        if total_accounts == 0:
            self.stdout.write(self.style.WARNING("No Threads accounts found to check"))
            logger.info("Threads token refresh: No accounts found")
            return

        self.stdout.write(f"Found {total_accounts} Threads account(s) to check")
        logger.info(f"Starting Threads token refresh for {total_accounts} account(s)")

        for account in all_accounts:
            accounts_checked += 1

            # Refresh if expiring within 10 days, or if we have no expiry on record at all.
            needs_refresh = account.expires_at is None or account.is_token_expiring(days=10)

            if needs_refresh:
                self.stdout.write(self.style.WARNING(
                    f"[{accounts_checked}/{total_accounts}] Token for {account.username} expires soon. Refreshing..."
                ))
                logger.warning(f"Threads token expiring soon for {account.username}, attempting refresh")

                try:
                    success = refresh_threads_token(account)
                except Exception as e:
                    logger.exception(f"Unexpected error refreshing Threads token for {account.username}: {e}")
                    success = False

                if success:
                    self.stdout.write(self.style.SUCCESS(
                        f"[{accounts_checked}/{total_accounts}] Token refreshed for {account.username}"
                    ))
                    logger.info(f"Threads token successfully refreshed for {account.username}")
                    tokens_refreshed += 1
                else:
                    self.stdout.write(self.style.ERROR(
                        f"[{accounts_checked}/{total_accounts}] Failed to refresh token for {account.username}"
                    ))
                    logger.error(f"Threads token refresh failed for {account.username}")
                    refresh_failures += 1
            else:
                expires_at = account.expires_at
                if expires_at:
                    days_until_expiry = (expires_at - now()).days
                    logger.debug(f"Threads token for {account.username} valid for {days_until_expiry} more days")

        end_time = now()
        duration = (end_time - start_time).total_seconds()

        summary = (
            f"\n{'='*60}\n"
            f"Threads Token Refresh Summary\n"
            f"{'='*60}\n"
            f"Accounts checked: {accounts_checked}\n"
            f"Tokens refreshed: {tokens_refreshed}\n"
            f"Refresh failures: {refresh_failures}\n"
            f"Duration: {duration:.2f}s\n"
            f"{'='*60}"
        )

        self.stdout.write(self.style.SUCCESS(summary))
        logger.info(
            f"Threads token refresh complete: checked={accounts_checked}, "
            f"refreshed={tokens_refreshed}, failed={refresh_failures}"
        )

        if refresh_failures > 0:
            warning_msg = f"{refresh_failures} Threads token refresh(es) failed. Check logs for details."
            self.stdout.write(self.style.WARNING(warning_msg))
            logger.warning(warning_msg)
