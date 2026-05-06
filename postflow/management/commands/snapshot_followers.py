"""
Management command to snapshot follower counts for all connected accounts.
Runs daily via APScheduler.
Usage: uv run manage.py snapshot_followers
"""
import logging
import requests
from datetime import date
from django.core.management.base import BaseCommand
from postflow.models import FollowerSnapshot

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = "Snapshot follower/following/post counts for all connected accounts"

    def handle(self, *args, **options):
        today = date.today()
        created = 0

        # Pixelfed/Mastodon-compatible accounts
        from pixelfed.models import MastodonAccount
        for account in MastodonAccount.objects.all():
            try:
                headers = {"Authorization": f"Bearer {account.access_token}"}
                resp = requests.get(
                    f"{account.instance_url}/api/v1/accounts/verify_credentials",
                    headers=headers, timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    _, was_created = FollowerSnapshot.objects.update_or_create(
                        user=account.user,
                        platform="pixelfed" if "pixelfed" in account.instance_url.lower() else "mastodon",
                        account_username=account.username,
                        date=today,
                        defaults={
                            "instance_url": account.instance_url,
                            "followers_count": data.get("followers_count", 0),
                            "following_count": data.get("following_count", 0),
                            "posts_count": data.get("statuses_count", 0),
                        },
                    )
                    if was_created:
                        created += 1
            except Exception as e:
                logger.error(f"Failed to snapshot {account.username}: {e}")

        # Native Mastodon accounts
        from mastodon_native.models import MastodonAccount as MastodonNativeAccount
        for account in MastodonNativeAccount.objects.all():
            try:
                from mastodon import Mastodon
                client = Mastodon(access_token=account.access_token, api_base_url=account.instance_url)
                data = client.account_verify_credentials()
                _, was_created = FollowerSnapshot.objects.update_or_create(
                    user=account.user,
                    platform="mastodon_native",
                    account_username=account.username,
                    date=today,
                    defaults={
                        "instance_url": account.instance_url,
                        "followers_count": data.get("followers_count", 0),
                        "following_count": data.get("following_count", 0),
                        "posts_count": data.get("statuses_count", 0),
                    },
                )
                if was_created:
                    created += 1
            except Exception as e:
                logger.error(f"Failed to snapshot Mastodon {account.username}: {e}")

        # Instagram accounts
        from instagram.models import InstagramBusinessAccount
        for account in InstagramBusinessAccount.objects.all():
            try:
                resp = requests.get(
                    f"https://graph.instagram.com/v22.0/{account.instagram_id}",
                    params={
                        "fields": "followers_count,follows_count,media_count",
                        "access_token": account.access_token,
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    _, was_created = FollowerSnapshot.objects.update_or_create(
                        user=account.user,
                        platform="instagram",
                        account_username=account.username,
                        date=today,
                        defaults={
                            "followers_count": data.get("followers_count", 0),
                            "following_count": data.get("follows_count", 0),
                            "posts_count": data.get("media_count", 0),
                        },
                    )
                    if was_created:
                        created += 1
            except Exception as e:
                logger.error(f"Failed to snapshot Instagram {account.username}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Created {created} follower snapshots"))
