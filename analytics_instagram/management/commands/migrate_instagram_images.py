"""
Management command to migrate Instagram analytics images from static bucket to media bucket.

This command re-downloads all Instagram post images and saves them using the correct
storage backend (media bucket with signed URLs instead of static bucket).

Usage:
    python manage.py migrate_instagram_images
    python manage.py migrate_instagram_images --dry-run  # Preview without making changes
    python manage.py migrate_instagram_images --limit 10  # Process only 10 posts
"""
import logging
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from analytics_instagram.models import InstagramPost

logger = logging.getLogger('postflow')


class Command(BaseCommand):
    help = 'Migrate Instagram analytics images from static bucket to media bucket'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without actually migrating images',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of posts to process',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-download and migrate even if cached_image already exists',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options.get('limit')
        force = options['force']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get all posts with images
        posts = InstagramPost.objects.filter(media_type__in=['IMAGE', 'CAROUSEL_ALBUM'])

        if not force:
            # Only process posts without cached images
            posts = posts.filter(cached_image='')

        posts = posts.order_by('-posted_at')

        if limit:
            posts = posts[:limit]

        total = posts.count()
        self.stdout.write(f'Found {total} posts to process')

        if total == 0:
            self.stdout.write(self.style.SUCCESS('No posts to migrate'))
            return

        success_count = 0
        skip_count = 0
        error_count = 0

        for i, post in enumerate(posts, 1):
            self.stdout.write(f'\n[{i}/{total}] Processing post {post.instagram_media_id}')

            # Check if post has a media_url
            if not post.media_url:
                self.stdout.write(self.style.WARNING(f'  ⚠ Skipping - no media_url'))
                skip_count += 1
                continue

            # Check if we should skip (already has cached image and not forcing)
            if post.cached_image and not force:
                self.stdout.write(self.style.WARNING(f'  ⚠ Skipping - already has cached_image'))
                skip_count += 1
                continue

            if dry_run:
                self.stdout.write(f'  Would download from: {post.media_url}')
                success_count += 1
                continue

            # Download and save image
            try:
                self.stdout.write(f'  Downloading from Instagram CDN...')
                response = requests.get(post.media_url, timeout=30)
                response.raise_for_status()

                # Get file extension from content type or URL
                content_type = response.headers.get('content-type', '')
                if 'image/jpeg' in content_type or 'image/jpg' in content_type:
                    ext = 'jpg'
                elif 'image/png' in content_type:
                    ext = 'png'
                else:
                    ext = 'jpg'  # Fallback

                # Create filename
                filename = f"{post.instagram_media_id}.{ext}"

                # Delete old cached_image if it exists
                if post.cached_image:
                    self.stdout.write(f'  Deleting old cached image...')
                    old_name = post.cached_image.name
                    post.cached_image.delete(save=False)
                    self.stdout.write(f'  Deleted: {old_name}')

                # Save to the cached_image field (will upload to media bucket)
                self.stdout.write(f'  Saving to media bucket...')
                post.cached_image.save(
                    filename,
                    ContentFile(response.content),
                    save=True
                )

                self.stdout.write(self.style.SUCCESS(f'  ✓ Successfully migrated: {post.cached_image.name}'))
                success_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error: {str(e)}'))
                logger.error(f"Failed to migrate image for post {post.instagram_media_id}: {e}")
                error_count += 1

        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'\nMigration Summary:'))
        self.stdout.write(f'  Total processed: {total}')
        self.stdout.write(self.style.SUCCESS(f'  Successful: {success_count}'))
        if skip_count > 0:
            self.stdout.write(self.style.WARNING(f'  Skipped: {skip_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'  Errors: {error_count}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No actual changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('\nMigration complete!'))
