"""
Management command to sync posts from all connected social media accounts.

This command runs the sync for Instagram, Pixelfed, and Mastodon in sequence,
importing all posts published outside of PostFlow so users can view complete
analytics for all their social media content.

Usage:
    python manage.py sync_all_posts
    python manage.py sync_all_posts --limit 50
"""
import logging
from django.core.management.base import BaseCommand
from django.core.management import call_command

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Sync posts from all connected social media accounts (Instagram, Pixelfed, Mastodon)'

    def add_arguments(self, parser):
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
        limit = options.get('limit', 50)
        force = options.get('force', False)

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('  Syncing All Social Media Posts'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))

        # Sync Instagram posts
        self.stdout.write(self.style.SUCCESS('1/3 Syncing Instagram posts...'))
        try:
            call_command('sync_instagram_posts', limit=limit, force=force)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Instagram sync failed: {e}'))
            logger.exception("Instagram sync failed")

        # Sync Pixelfed posts
        self.stdout.write(self.style.SUCCESS('\n2/3 Syncing Pixelfed posts...'))
        try:
            call_command('sync_pixelfed_posts', limit=limit, force=force)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Pixelfed sync failed: {e}'))
            logger.exception("Pixelfed sync failed")

        # Sync Mastodon posts
        self.stdout.write(self.style.SUCCESS('\n3/3 Syncing Mastodon posts...'))
        try:
            call_command('sync_mastodon_posts', limit=limit, force=force)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Mastodon sync failed: {e}'))
            logger.exception("Mastodon sync failed")

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('  Sync Complete!'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
