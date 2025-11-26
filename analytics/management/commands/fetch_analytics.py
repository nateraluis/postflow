"""
Management command to fetch analytics for posted content.

Usage:
    python manage.py fetch_analytics
    python manage.py fetch_analytics --post-id 123
    python manage.py fetch_analytics --days 7
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from postflow.models import ScheduledPost
from analytics.models import PostAnalytics
from analytics.utils import (
    fetch_instagram_analytics,
    fetch_mastodon_analytics,
    fetch_pixelfed_analytics,
    AnalyticsFetchError
)

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Fetch analytics for posted content from Instagram, Mastodon, and Pixelfed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--post-id',
            type=int,
            help='Fetch analytics for a specific post ID'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Fetch analytics for posts from the last N days (default: 7)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refetch analytics even if recently updated'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        post_id = options.get('post_id')
        days = options.get('days')
        force = options.get('force')

        if post_id:
            # Fetch analytics for a specific post
            try:
                post = ScheduledPost.objects.get(id=post_id)
                self.fetch_post_analytics(post, force=force)
            except ScheduledPost.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Post with ID {post_id} not found')
                )
                return
        else:
            # Fetch analytics for recent posted posts
            cutoff_date = timezone.now() - timedelta(days=days)
            posts = ScheduledPost.objects.filter(
                status='posted',
                post_date__gte=cutoff_date
            ).order_by('-post_date')

            total = posts.count()
            self.stdout.write(
                self.style.SUCCESS(f'Found {total} posted post(s) from the last {days} days')
            )

            if total == 0:
                self.stdout.write(
                    self.style.WARNING('No posts to fetch analytics for')
                )
                return

            success_count = 0
            error_count = 0

            for post in posts:
                try:
                    self.fetch_post_analytics(post, force=force)
                    success_count += 1
                except Exception as e:
                    logger.exception(f"Failed to fetch analytics for post {post.id}: {e}")
                    error_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'\nCompleted: {success_count} successful, {error_count} failed'
                )
            )

    def fetch_post_analytics(self, post: ScheduledPost, force: bool = False):
        """
        Fetch analytics for a single post across all platforms.

        Args:
            post: ScheduledPost instance
            force: Force refetch even if recently updated
        """
        self.stdout.write(f'\nProcessing post {post.id}: {post.caption[:50] if post.caption else "No caption"}...')

        # Fetch Instagram analytics
        if post.instagram_accounts.exists() and post.instagram_post_id:
            for account in post.instagram_accounts.all():
                self.fetch_platform_analytics(
                    post=post,
                    platform='instagram',
                    platform_post_id=post.instagram_post_id,
                    access_token=account.access_token,
                    instance_url=None,
                    force=force
                )

        # Fetch Mastodon analytics (native accounts)
        if post.mastodon_native_accounts.exists() and post.mastodon_post_id:
            for account in post.mastodon_native_accounts.all():
                self.fetch_platform_analytics(
                    post=post,
                    platform='mastodon',
                    platform_post_id=post.mastodon_post_id,
                    access_token=account.access_token,
                    instance_url=account.instance_url,
                    force=force
                )

        # Fetch Pixelfed analytics
        if post.mastodon_accounts.exists() and post.pixelfed_post_id:
            for account in post.mastodon_accounts.all():
                self.fetch_platform_analytics(
                    post=post,
                    platform='pixelfed',
                    platform_post_id=post.pixelfed_post_id,
                    access_token=account.access_token,
                    instance_url=account.instance_url,
                    force=force
                )

    def fetch_platform_analytics(
        self,
        post: ScheduledPost,
        platform: str,
        platform_post_id: str,
        access_token: str,
        instance_url: str = None,
        force: bool = False
    ):
        """
        Fetch and save analytics for a specific platform.

        Args:
            post: ScheduledPost instance
            platform: Platform name ('instagram', 'mastodon', 'pixelfed')
            platform_post_id: ID of the post on the platform
            access_token: Access token for API
            instance_url: Instance URL (for Mastodon/Pixelfed)
            force: Force refetch
        """
        try:
            # Check if analytics already exist
            analytics, created = PostAnalytics.objects.get_or_create(
                scheduled_post=post,
                platform=platform,
                platform_post_id=platform_post_id,
                defaults={'likes': 0, 'comments': 0, 'shares': 0}
            )

            # Skip if recently updated (unless force)
            if not force and not created:
                time_since_update = timezone.now() - analytics.last_updated
                if time_since_update < timedelta(hours=1):
                    self.stdout.write(
                        f'  ⏭️  Skipping {platform} (updated {time_since_update.seconds // 60} min ago)'
                    )
                    return

            # Fetch analytics from API
            if platform == 'instagram':
                metrics = fetch_instagram_analytics(platform_post_id, access_token)
            elif platform == 'mastodon':
                metrics = fetch_mastodon_analytics(platform_post_id, instance_url, access_token)
            elif platform == 'pixelfed':
                metrics = fetch_pixelfed_analytics(platform_post_id, instance_url, access_token)
            else:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Unknown platform: {platform}')
                )
                return

            # Update analytics
            analytics.likes = metrics['likes']
            analytics.comments = metrics['comments']
            analytics.shares = metrics['shares']
            analytics.impressions = metrics.get('impressions')
            analytics.reach = metrics.get('reach')
            analytics.saved = metrics.get('saved', 0)
            analytics.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f'  ✓ {platform.title()}: {analytics.likes} likes, '
                    f'{analytics.comments} comments, {analytics.shares} shares'
                )
            )

        except AnalyticsFetchError as e:
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  {platform.title()} API error: {e}')
            )
            # Don't raise - just log and continue with other platforms
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  {platform.title()} error: {e}')
            )
            # Don't raise - just log and continue with other platforms
