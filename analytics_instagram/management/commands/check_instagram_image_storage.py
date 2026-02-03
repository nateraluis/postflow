"""
Management command to check where Instagram analytics images are stored.

This command inspects InstagramPost records to see which bucket their cached_image
files are in, and verifies the current storage configuration.

Usage:
    python manage.py check_instagram_image_storage
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from analytics_instagram.models import InstagramPost


class Command(BaseCommand):
    help = 'Check Instagram analytics image storage locations'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Storage Configuration Check ===\n'))

        # Check current storage settings
        self.stdout.write('Current Storage Backend:')
        if hasattr(settings, 'STORAGES'):
            default_storage = settings.STORAGES.get('default', {})
            self.stdout.write(f'  Backend: {default_storage.get("BACKEND", "Not configured")}')
            storage_options = default_storage.get('OPTIONS', {})
            self.stdout.write(f'  Bucket: {storage_options.get("bucket_name", "Not configured")}')
            self.stdout.write(f'  Region: {storage_options.get("region_name", "Not configured")}')
        else:
            self.stdout.write('  STORAGES not configured')

        # Get sample posts with images
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('\n=== Sample Instagram Posts ===\n'))

        posts_with_images = InstagramPost.objects.filter(
            cached_image__isnull=False
        ).exclude(cached_image='').order_by('-posted_at')[:5]

        if not posts_with_images:
            self.stdout.write(self.style.WARNING('No posts with cached images found'))
            return

        for i, post in enumerate(posts_with_images, 1):
            self.stdout.write(f'\nPost {i}: {post.instagram_media_id}')
            self.stdout.write(f'  Posted: {post.posted_at}')
            self.stdout.write(f'  Cached Image Path: {post.cached_image.name}')

            # Try to get the URL
            try:
                url = post.get_display_image_url()
                self.stdout.write(f'  Image URL: {url[:100]}...' if len(url) > 100 else f'  Image URL: {url}')

                # Check which bucket the URL points to
                if 'postflow-static' in url:
                    self.stdout.write(self.style.ERROR('  ❌ WRONG BUCKET: Using static bucket'))
                elif 'postflow-media' in url or settings.AWS_STORAGE_MEDIA_BUCKET_NAME in url:
                    self.stdout.write(self.style.SUCCESS('  ✓ CORRECT: Using media bucket'))
                else:
                    self.stdout.write(self.style.WARNING('  ⚠ Unknown bucket'))

                # Check for signed URL
                if 'X-Amz-Algorithm' in url or 'Signature=' in url:
                    self.stdout.write(self.style.SUCCESS('  ✓ Signed URL detected'))
                else:
                    self.stdout.write(self.style.WARNING('  ⚠ No signed URL parameters'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error getting URL: {e}'))

        # Summary
        self.stdout.write('\n' + '='*60)
        total_with_images = InstagramPost.objects.filter(
            cached_image__isnull=False
        ).exclude(cached_image='').count()
        self.stdout.write(f'\nTotal posts with cached images: {total_with_images}')

        self.stdout.write('\n' + self.style.SUCCESS('Check complete!'))
        self.stdout.write('\nIf images are in the wrong bucket:')
        self.stdout.write('  1. Ensure settings are deployed')
        self.stdout.write('  2. Restart Django: docker-compose restart django')
        self.stdout.write('  3. Run: python manage.py migrate_instagram_images --force')
