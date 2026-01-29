"""
Management command to sync posts from Pixelfed accounts.

Fetches posts from connected Pixelfed accounts and creates/updates
PixelfedPost records for analytics tracking.
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from pixelfed.models import MastodonAccount
from analytics_pixelfed.fetcher import PixelfedAnalyticsFetcher, PixelfedAPIError

logger = logging.getLogger('postflow')
User = get_user_model()


class Command(BaseCommand):
    help = 'Sync posts from Pixelfed accounts for analytics tracking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Specific MastodonAccount ID to sync (optional)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of posts to fetch per account. Use 0 or --all for unlimited (default: 50)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fetch ALL posts from the account (ignores --limit)'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Email of user whose accounts to sync (optional)'
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        fetch_all = options.get('all', False)
        limit = options['limit']
        user_email = options.get('user')

        # Handle --all flag or limit=0 for unlimited fetch
        if fetch_all or limit == 0:
            limit = None
            self.stdout.write(self.style.WARNING("Fetching ALL posts (unlimited)"))

        # Determine which accounts to sync
        if account_id:
            # Sync specific account
            try:
                account = MastodonAccount.objects.get(id=account_id)
                accounts = [account]
                self.stdout.write(f"Syncing posts for account: {account}")
            except MastodonAccount.DoesNotExist:
                raise CommandError(f"MastodonAccount with ID {account_id} does not exist")

        elif user_email:
            # Sync all accounts for specific user
            try:
                user = User.objects.get(email=user_email)
                accounts = MastodonAccount.objects.filter(user=user)
                if not accounts.exists():
                    raise CommandError(f"No Pixelfed accounts found for user {user_email}")
                self.stdout.write(f"Found {accounts.count()} accounts for user {user_email}")
            except User.DoesNotExist:
                raise CommandError(f"User with email {user_email} does not exist")

        else:
            # Sync all Pixelfed accounts
            accounts = MastodonAccount.objects.all()
            if not accounts.exists():
                self.stdout.write(self.style.WARNING("No Pixelfed accounts found"))
                return
            self.stdout.write(f"Found {accounts.count()} total Pixelfed accounts to sync")

        # Track overall statistics
        total_created = 0
        total_updated = 0
        total_errors = []

        # Process each account
        for account in accounts:
            self.stdout.write(f"\nProcessing account: {account}")
            self.stdout.write(f"  Instance: {account.instance_url}")
            self.stdout.write(f"  Username: {account.username}")

            try:
                fetcher = PixelfedAnalyticsFetcher(account)
                created, updated = fetcher.sync_account_posts(limit=limit)

                total_created += created
                total_updated += updated

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Synced: {created} new posts, {updated} updated posts"
                    )
                )

            except PixelfedAPIError as e:
                error_msg = f"API error for {account}: {e}"
                logger.error(error_msg)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ {e}"))

            except Exception as e:
                error_msg = f"Unexpected error for {account}: {e}"
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