"""
Management command to create PixelfedEngagementSummary for posts that don't have one.

This is useful for existing posts that were created before the signal was added.
"""
from django.core.management.base import BaseCommand
from analytics_pixelfed.models import PixelfedPost, PixelfedEngagementSummary


class Command(BaseCommand):
    help = 'Create PixelfedEngagementSummary for posts that don\'t have one'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find posts without engagement summary
        posts_without_summary = PixelfedPost.objects.filter(
            engagement_summary__isnull=True
        )

        count = posts_without_summary.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('All posts already have engagement summaries!'))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'[DRY RUN] Would create engagement summaries for {count} posts')
            )
            return

        # Create engagement summaries
        created = 0
        for post in posts_without_summary:
            summary, was_created = PixelfedEngagementSummary.objects.get_or_create(post=post)
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created} engagement summaries')
        )
