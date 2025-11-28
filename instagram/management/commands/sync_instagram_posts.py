"""
Management command to sync Instagram posts that were published outside of PostFlow.

This command fetches all posts from connected Instagram Business accounts and creates
ScheduledPost records for any posts not already in the system. This allows users to
view analytics for all their Instagram content in one place.

Usage:
    python manage.py sync_instagram_posts
    python manage.py sync_instagram_posts --account-id 123
    python manage.py sync_instagram_posts --limit 50
"""
import logging
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from instagram.models import InstagramBusinessAccount
from postflow.models import ScheduledPost

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Sync Instagram posts from connected accounts into PostFlow'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Sync posts from a specific Instagram account ID'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of posts to fetch per account (default: 50)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-sync even for posts that already exist'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        account_id = options.get('account_id')
        limit = options.get('limit', 50)
        force = options.get('force', False)

        self.stdout.write(self.style.SUCCESS('\n=== Instagram Post Sync ===\n'))

        # Get accounts to sync
        if account_id:
            accounts = InstagramBusinessAccount.objects.filter(id=account_id)
            if not accounts.exists():
                self.stdout.write(
                    self.style.ERROR(f'Instagram account with ID {account_id} not found')
                )
                return
        else:
            accounts = InstagramBusinessAccount.objects.all()

        total_accounts = accounts.count()
        if total_accounts == 0:
            self.stdout.write(self.style.WARNING('No Instagram accounts found'))
            return

        self.stdout.write(f'Found {total_accounts} Instagram account(s) to sync\n')

        total_synced = 0
        total_skipped = 0
        total_errors = 0

        for account in accounts:
            self.stdout.write(f'\n{self.style.SUCCESS(f"Syncing @{account.username}...")}')

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
                logger.exception(f"Error syncing Instagram account {account.id}")
                total_errors += 1

        # Summary
        self.stdout.write(f'\n{self.style.SUCCESS("=== Sync Complete ===")}')
        self.stdout.write(f'Total posts synced: {total_synced}')
        self.stdout.write(f'Total posts skipped: {total_skipped}')
        self.stdout.write(f'Total errors: {total_errors}\n')

    def sync_account_posts(self, account: InstagramBusinessAccount, limit: int, force: bool):
        """
        Sync posts from a single Instagram account.

        Returns:
            tuple: (synced_count, skipped_count, error_count)
        """
        synced = 0
        skipped = 0
        errors = 0

        # Fetch posts from Instagram API
        media_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}/media"
        params = {
            'fields': 'id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count',
            'limit': limit,
            'access_token': account.access_token
        }

        try:
            response = requests.get(media_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            media_items = data.get('data', [])
            self.stdout.write(f'  Found {len(media_items)} posts on Instagram')

            for media in media_items:
                try:
                    # Check if we already have this post
                    instagram_post_id = media.get('id')

                    if not force:
                        existing_post = ScheduledPost.objects.filter(
                            instagram_post_id=instagram_post_id
                        ).first()

                        if existing_post:
                            skipped += 1
                            continue

                    # Parse timestamp
                    timestamp_str = media.get('timestamp')
                    if timestamp_str:
                        post_date = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        post_date = timezone.now()

                    # Get media type and URL
                    media_type = media.get('media_type')
                    media_url_str = media.get('media_url')

                    # Only sync IMAGE and CAROUSEL posts (not VIDEO for now)
                    if media_type not in ['IMAGE', 'CAROUSEL_ALBUM']:
                        self.stdout.write(
                            f'  ⏭️  Skipping {media_type} post {instagram_post_id}'
                        )
                        skipped += 1
                        continue

                    # Create ScheduledPost record
                    with transaction.atomic():
                        post = ScheduledPost.objects.create(
                            user=account.user,
                            caption=media.get('caption', ''),
                            post_date=post_date,
                            status='posted',
                            instagram_post_id=instagram_post_id,
                            instagram_media_id=instagram_post_id,
                            user_timezone=str(timezone.get_current_timezone())
                        )

                        # Link to Instagram account
                        post.instagram_accounts.add(account)

                        synced += 1
                        self.stdout.write(
                            f'  ✓ Synced post {instagram_post_id} from {post_date.strftime("%Y-%m-%d")}'
                        )

                except Exception as e:
                    errors += 1
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠️  Error processing post: {e}')
                    )
                    logger.error(f"Error processing Instagram post: {e}")

        except requests.exceptions.RequestException as e:
            self.stdout.write(
                self.style.ERROR(f'  ✗ API error: {e}')
            )
            logger.error(f"Instagram API error for account {account.id}: {e}")
            errors += 1

        return synced, skipped, errors
