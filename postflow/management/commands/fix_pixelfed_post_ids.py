"""
Management command to fix incorrect pixelfed_post_id values.

This command clears pixelfed_post_id for posts that were posted to non-Pixelfed
Mastodon-compatible instances, as those posts have Mastodon post IDs incorrectly
stored in the pixelfed_post_id field.

Usage:
    python manage.py fix_pixelfed_post_ids
    python manage.py fix_pixelfed_post_ids --dry-run
"""
import logging
from django.core.management.base import BaseCommand
from postflow.models import ScheduledPost

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Fix incorrect pixelfed_post_id values in existing posts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        # Find all posted posts with mastodon accounts
        all_posted_posts = ScheduledPost.objects.filter(
            status='posted',
            mastodon_accounts__isnull=False
        ).distinct().prefetch_related('mastodon_accounts')

        self.stdout.write(f'Found {all_posted_posts.count()} posted post(s) with mastodon accounts')

        # Find posts with pixelfed_post_id set
        posts_with_pixelfed_id = ScheduledPost.objects.filter(
            pixelfed_post_id__isnull=False
        ).prefetch_related('mastodon_accounts')

        total_posts = posts_with_pixelfed_id.count()
        self.stdout.write(f'Found {total_posts} post(s) with pixelfed_post_id set')

        if total_posts == 0:
            self.stdout.write(self.style.SUCCESS('No posts to fix'))
            return

        fixed_count = 0

        for post in posts_with_pixelfed_id:
            # Check if this post was posted to any non-Pixelfed instances
            has_non_pixelfed = False
            has_pixelfed = False

            pixelfed_accounts = []
            non_pixelfed_accounts = []

            for account in post.mastodon_accounts.all():
                is_pixelfed = "pixelfed" in account.instance_url.lower()
                if is_pixelfed:
                    has_pixelfed = True
                    pixelfed_accounts.append(account.instance_url)
                else:
                    has_non_pixelfed = True
                    non_pixelfed_accounts.append(account.instance_url)

            # Debug output for first few posts
            if dry_run and fixed_count < 5:
                self.stdout.write(
                    f'\n  Post {post.id}:'
                    f'\n    pixelfed_post_id: {post.pixelfed_post_id}'
                    f'\n    mastodon_post_id: {post.mastodon_post_id}'
                    f'\n    Pixelfed accounts: {pixelfed_accounts}'
                    f'\n    Non-Pixelfed accounts: {non_pixelfed_accounts}'
                    f'\n    has_pixelfed: {has_pixelfed}, has_non_pixelfed: {has_non_pixelfed}'
                    f'\n    IDs match: {post.pixelfed_post_id == post.mastodon_post_id}'
                )

            # If pixelfed_post_id is set but post was only sent to non-Pixelfed instances,
            # or if pixelfed_post_id matches mastodon_post_id (indicating wrong ID),
            # clear it
            should_fix = False
            reason = ""

            if not has_pixelfed and post.pixelfed_post_id:
                # Post only went to non-Pixelfed instances
                should_fix = True
                reason = "Post only sent to non-Pixelfed instances"
            elif has_pixelfed and has_non_pixelfed and post.pixelfed_post_id == post.mastodon_post_id:
                # Post sent to both, but IDs are the same (one overwrote the other)
                should_fix = True
                reason = "Sent to both but pixelfed_post_id matches mastodon_post_id"

            if should_fix:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Post {post.id}: {reason}. '
                        f'Clearing pixelfed_post_id={post.pixelfed_post_id}'
                    )
                )

                if not dry_run:
                    post.pixelfed_post_id = None
                    post.save(update_fields=['pixelfed_post_id'])

                fixed_count += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDRY RUN: Would fix {fixed_count} post(s)'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nFixed {fixed_count} post(s)'
                )
            )
