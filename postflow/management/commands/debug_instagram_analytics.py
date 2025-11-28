"""
Management command to debug Instagram analytics issues.

Usage:
    python manage.py debug_instagram_analytics --post-id 61
"""
import logging
import requests
from django.core.management.base import BaseCommand
from postflow.models import ScheduledPost

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Debug Instagram analytics issues for a specific post'

    def add_arguments(self, parser):
        parser.add_argument(
            '--post-id',
            type=int,
            required=True,
            help='Post ID to debug'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        post_id = options.get('post_id')

        try:
            post = ScheduledPost.objects.get(id=post_id)
        except ScheduledPost.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Post with ID {post_id} not found')
            )
            return

        self.stdout.write(f'\n{self.style.SUCCESS("Post Information:")}')
        self.stdout.write(f'  ID: {post.id}')
        self.stdout.write(f'  Caption: {post.caption[:50] if post.caption else "No caption"}...')
        self.stdout.write(f'  Status: {post.status}')
        self.stdout.write(f'  Post Date: {post.post_date}')
        self.stdout.write(f'  Instagram Post ID: {post.instagram_post_id}')
        self.stdout.write(f'  Instagram Media ID: {post.instagram_media_id}')

        # Check Instagram accounts
        instagram_accounts = post.instagram_accounts.all()
        self.stdout.write(f'\n{self.style.SUCCESS("Instagram Accounts:")}')

        if not instagram_accounts:
            self.stdout.write(self.style.WARNING('  No Instagram accounts linked to this post'))
            return

        for account in instagram_accounts:
            self.stdout.write(f'\n  Account: @{account.username}')
            self.stdout.write(f'  Instagram ID: {account.instagram_id}')
            self.stdout.write(f'  Token expires: {account.expires_at}')
            self.stdout.write(f'  Last refreshed: {account.last_refreshed_at}')

            # Test the access token
            self.stdout.write(f'\n  {self.style.SUCCESS("Testing Access Token:")}')
            test_url = f"https://graph.facebook.com/v18.0/me"
            test_params = {
                'access_token': account.access_token,
                'fields': 'id,name'
            }

            try:
                response = requests.get(test_url, params=test_params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    self.stdout.write(f'    ✓ Token valid - Account: {data.get("name")} (ID: {data.get("id")})')
                else:
                    self.stdout.write(
                        self.style.ERROR(f'    ✗ Token invalid - Status: {response.status_code}')
                    )
                    self.stdout.write(f'    Response: {response.text[:200]}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    ✗ Error testing token: {e}'))

            # Test fetching the specific post
            if post.instagram_post_id:
                self.stdout.write(f'\n  {self.style.SUCCESS("Testing Post Access:")}')
                post_url = f"https://graph.facebook.com/v18.0/{post.instagram_post_id}"
                post_params = {
                    'fields': 'id,media_type,permalink,timestamp',
                    'access_token': account.access_token
                }

                try:
                    response = requests.get(post_url, params=post_params, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        self.stdout.write(f'    ✓ Post accessible')
                        self.stdout.write(f'    Media Type: {data.get("media_type")}')
                        self.stdout.write(f'    Permalink: {data.get("permalink")}')
                        self.stdout.write(f'    Timestamp: {data.get("timestamp")}')
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'    ✗ Cannot access post - Status: {response.status_code}')
                        )
                        self.stdout.write(f'    Response: {response.text[:500]}')

                        # Try to parse error
                        try:
                            error_data = response.json()
                            if 'error' in error_data:
                                error_msg = error_data['error'].get('message', 'Unknown error')
                                error_code = error_data['error'].get('code', 'Unknown code')
                                self.stdout.write(f'    Error: {error_msg} (Code: {error_code})')
                        except:
                            pass

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'    ✗ Error fetching post: {e}'))
