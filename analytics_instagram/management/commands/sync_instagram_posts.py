"""
Management command to sync posts from Instagram Business accounts.

Fetches posts from connected Instagram Business accounts and creates/updates
InstagramPost records for analytics tracking.
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from instagram.models import InstagramBusinessAccount
from analytics_instagram.fetcher import InstagramAnalyticsFetcher, InstagramAPIError

logger = logging.getLogger('postflow')
User = get_user_model()


class Command(BaseCommand):
    help = 'Sync posts from Instagram Business accounts for analytics tracking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Specific InstagramBusinessAccount ID to sync (optional)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of posts to fetch per account (default 50)'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Email of user whose accounts to sync (optional)'
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        limit = options.get('limit')
        user_email = options.get('user')

        self.stdout.write(f"Fetching up to {limit} posts per account")

        # Determine which accounts to sync
        if account_id:
            # Sync specific account
            try:
                account = InstagramBusinessAccount.objects.get(id=account_id)
                accounts = [account]
                self.stdout.write(f"Syncing posts for account: @{account.username}")
            except InstagramBusinessAccount.DoesNotExist:
                raise CommandError(f"InstagramBusinessAccount with ID {account_id} does not exist")

        elif user_email:
            # Sync all accounts for specific user
            try:
                user = User.objects.get(email=user_email)
                accounts = InstagramBusinessAccount.objects.filter(user=user)
                if not accounts.exists():
                    raise CommandError(f"No Instagram Business accounts found for user {user_email}")
                self.stdout.write(f"Found {accounts.count()} accounts for user {user_email}")
            except User.DoesNotExist:
                raise CommandError(f"User with email {user_email} does not exist")

        else:
            # Sync all Instagram Business accounts
            accounts = InstagramBusinessAccount.objects.all()
            if not accounts.exists():
                self.stdout.write(self.style.WARNING("No Instagram Business accounts found"))
                return
            self.stdout.write(f"Found {accounts.count()} Instagram Business accounts to sync")

        # Track overall statistics
        total_created = 0
        total_updated = 0
        total_errors = []

        # Process each account
        for account in accounts:
            self.stdout.write(f"\nProcessing account: @{account.username}")
            self.stdout.write(f"  Instagram ID: {account.instagram_id}")

            try:
                fetcher = InstagramAnalyticsFetcher(account)
                created, updated = fetcher.sync_account_posts(limit=limit)

                total_created += created
                total_updated += updated

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Synced: {created} new posts, {updated} updated posts"
                    )
                )

            except InstagramAPIError as e:
                error_msg = f"API error for @{account.username}: {e}"
                logger.error(error_msg)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ {e}"))

            except Exception as e:
                error_msg = f"Unexpected error for @{account.username}: {e}"
                logger.error(error_msg, exc_info=True)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ Unexpected error: {e}"))

        # Print summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("SYNC SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Accounts processed: {accounts.count()}")
        self.stdout.write(f"Posts created: {total_created}")
        self.stdout.write(f"Posts updated: {total_updated}")
        self.stdout.write(f"Total posts: {total_created + total_updated}")

        if total_errors:
            self.stdout.write(self.style.WARNING(f"Errors encountered: {len(total_errors)}"))
            for error in total_errors[:5]:  # Show first 5 errors
                self.stdout.write(self.style.ERROR(f"  - {error}"))
            if len(total_errors) > 5:
                self.stdout.write(f"  ... and {len(total_errors) - 5} more errors")
        else:
            self.stdout.write(self.style.SUCCESS("No errors encountered"))

        self.stdout.write("="*50)

        # Log completion
        logger.info(
            f"Sync completed: {accounts.count()} accounts, "
            f"{total_created} created, {total_updated} updated, "
            f"{len(total_errors)} errors"
        )
