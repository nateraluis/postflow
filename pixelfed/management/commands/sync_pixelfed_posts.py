"""
Management command to sync Pixelfed posts that were published outside of PostFlow.

This command fetches all posts from connected Pixelfed accounts and creates
ScheduledPost records for any posts not already in the system. This allows users to
view analytics for all their Pixelfed content in one place.

Usage:
    python manage.py sync_pixelfed_posts
    python manage.py sync_pixelfed_posts --account-id 123
    python manage.py sync_pixelfed_posts --limit 40
"""
import logging
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from pixelfed.models import MastodonAccount
from postflow.models import ScheduledPost

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Sync Pixelfed posts from connected accounts into PostFlow'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Sync posts from a specific Pixelfed account ID'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=40,
            help='Maximum number of posts to fetch per account (default: 40)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-sync even for posts that already exist'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        account_id = options.get('account_id')
        limit = options.get('limit', 40)
        force = options.get('force', False)

        self.stdout.write(self.style.SUCCESS('\n=== Pixelfed Post Sync ===\n'))

        # Get accounts to sync (only Pixelfed instances)
        if account_id:
            accounts = MastodonAccount.objects.filter(id=account_id)
            if not accounts.exists():
                self.stdout.write(
                    self.style.ERROR(f'Pixelfed account with ID {account_id} not found')
                )
                return
        else:
            # Only sync from Pixelfed instances (not other Mastodon-compatible instances)
            accounts = MastodonAccount.objects.filter(
                instance_url__icontains='pixelfed'
            )

        total_accounts = accounts.count()
        if total_accounts == 0:
            self.stdout.write(self.style.WARNING('No Pixelfed accounts found'))
            return

        self.stdout.write(f'Found {total_accounts} Pixelfed account(s) to sync\n')

        total_synced = 0
        total_skipped = 0
        total_errors = 0

        for account in accounts:
            self.stdout.write(f'\n{self.style.SUCCESS(f"Syncing @{account.username} on {account.instance_url}...")}')

            try:
                synced, skipped, errors = self.sync_account_posts(
                    account, limit, force
                )
                total_synced += synced
                total_skipped += skipped
                total_errors += errors

                self.stdout.write(
                    f'  ✓ Synced: {synced}, Skipped: {skipped}, Errors: {errors}'
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error syncing @{account.username}: {e}')
                )
                logger.exception(f"Error syncing Pixelfed account {account.id}")
                total_errors += 1

        # Summary
        self.stdout.write(f'\n{self.style.SUCCESS("=== Sync Complete ===")}')
        self.stdout.write(f'Total posts synced: {total_synced}')
        self.stdout.write(f'Total posts skipped: {total_skipped}')
        self.stdout.write(f'Total errors: {total_errors}\n')

    def sync_account_posts(self, account, limit: int, force: bool):
        """
        Sync posts from a single Pixelfed account.

        Returns:
            tuple: (synced_count, skipped_count, error_count)
        """
        synced = 0
        skipped = 0
        errors = 0

        # Fetch user's account ID first
        instance_url = account.instance_url.rstrip('/')

        # Get account info to find the account ID
        verify_url = f"{instance_url}/api/v1/accounts/verify_credentials"
        headers = {'Authorization': f'Bearer {account.access_token}'}

        try:
            verify_response = requests.get(verify_url, headers=headers, timeout=10)
            verify_response.raise_for_status()
            account_data = verify_response.json()
            account_id = account_data.get('id')

            if not account_id:
                self.stdout.write(
                    self.style.ERROR('  ✗ Could not get account ID')
                )
                return 0, 0, 1

            # Fetch posts (statuses) from Pixelfed
            statuses_url = f"{instance_url}/api/v1/accounts/{account_id}/statuses"
            params = {
                'limit': limit,
                'exclude_replies': 'true',
                'exclude_reblogs': 'true'
            }

            response = requests.get(statuses_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            statuses = response.json()

            self.stdout.write(f'  Found {len(statuses)} posts on Pixelfed')

            for status in statuses:
                try:
                    # Check if we already have this post
                    pixelfed_post_id = status.get('id')

                    if not force:
                        existing_post = ScheduledPost.objects.filter(
                            pixelfed_post_id=pixelfed_post_id
                        ).first()

                        if existing_post:
                            skipped += 1
                            continue

                    # Parse timestamp
                    created_at = status.get('created_at')
                    if created_at:
                        post_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        post_date = timezone.now()

                    # Get caption/content
                    # Pixelfed returns HTML content, we need to strip it
                    from html import unescape
                    import re
                    content = status.get('content', '')
                    # Strip HTML tags
                    content = re.sub('<[^<]+?>', '', content)
                    content = unescape(content).strip()

                    # Create ScheduledPost record
                    with transaction.atomic():
                        post = ScheduledPost.objects.create(
                            user=account.user,
                            caption=content,
                            post_date=post_date,
                            status='posted',
                            pixelfed_post_id=pixelfed_post_id,
                            mastodon_post_id=pixelfed_post_id,  # Also set for backwards compatibility
                            user_timezone=str(timezone.get_current_timezone())
                        )

                        # Link to Pixelfed account
                        post.mastodon_accounts.add(account)

                        synced += 1
                        self.stdout.write(
                            f'  ✓ Synced post {pixelfed_post_id} from {post_date.strftime("%Y-%m-%d")}'
                        )

                except Exception as e:
                    errors += 1
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠️  Error processing post: {e}')
                    )
                    logger.error(f"Error processing Pixelfed post: {e}")

        except requests.exceptions.RequestException as e:
            self.stdout.write(
                self.style.ERROR(f'  ✗ API error: {e}')
            )
            logger.error(f"Pixelfed API error for account {account.id}: {e}")
            errors += 1

        return synced, skipped, errors
