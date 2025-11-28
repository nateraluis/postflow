"""
Management command to test Instagram access token.
"""
import logging
import requests
from django.core.management.base import BaseCommand
from instagram.models import InstagramBusinessAccount

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = 'Test Instagram access token with various API endpoints'

    def handle(self, *args, **options):
        """Execute the command."""
        accounts = InstagramBusinessAccount.objects.all()

        if not accounts:
            self.stdout.write(self.style.ERROR('No Instagram accounts found'))
            return

        for account in accounts:
            self.stdout.write(f'\n{self.style.SUCCESS(f"Testing account: @{account.username}")}')

            token = account.access_token
            self.stdout.write(f'  Token length: {len(token)} characters')
            self.stdout.write(f'  Token starts: {token[:30]}...')
            self.stdout.write(f'  Token ends: ...{token[-20:]}')
            self.stdout.write(f'  Has newlines: {("\\n" in token or "\\r" in token)}')
            self.stdout.write(f'  Has spaces: {" " in token}')

            # Test 1: Facebook Graph API /me endpoint
            self.stdout.write(f'\n  {self.style.SUCCESS("Test 1: Facebook Graph /me")}')
            test_url = f"https://graph.facebook.com/v18.0/me"
            try:
                response = requests.get(
                    test_url,
                    params={'access_token': token, 'fields': 'id,name'},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    self.stdout.write(f'    ✓ Success: {data}')
                else:
                    self.stdout.write(f'    ✗ Failed: {response.status_code}')
                    self.stdout.write(f'    Response: {response.text[:200]}')
            except Exception as e:
                self.stdout.write(f'    ✗ Error: {e}')

            # Test 2: Instagram Graph API account info
            self.stdout.write(f'\n  {self.style.SUCCESS("Test 2: Instagram Graph account")}')
            test_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}"
            try:
                response = requests.get(
                    test_url,
                    params={'access_token': token, 'fields': 'id,username'},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    self.stdout.write(f'    ✓ Success: {data}')
                else:
                    self.stdout.write(f'    ✗ Failed: {response.status_code}')
                    self.stdout.write(f'    Response: {response.text[:200]}')
            except Exception as e:
                self.stdout.write(f'    ✗ Error: {e}')

            # Test 3: Try to access a recent post
            from postflow.models import ScheduledPost
            recent_post = ScheduledPost.objects.filter(
                status='posted',
                instagram_accounts=account,
                instagram_post_id__isnull=False
            ).order_by('-post_date').first()

            if recent_post:
                self.stdout.write(f'\n  {self.style.SUCCESS(f"Test 3: Access post {recent_post.instagram_post_id}")}')
                test_url = f"https://graph.facebook.com/v18.0/{recent_post.instagram_post_id}"
                try:
                    response = requests.get(
                        test_url,
                        params={'access_token': token, 'fields': 'id,like_count'},
                        timeout=10
                    )
                    if response.status_code == 200:
                        data = response.json()
                        self.stdout.write(f'    ✓ Success: {data}')
                    else:
                        self.stdout.write(f'    ✗ Failed: {response.status_code}')
                        self.stdout.write(f'    Response: {response.text[:300]}')
                except Exception as e:
                    self.stdout.write(f'    ✗ Error: {e}')
