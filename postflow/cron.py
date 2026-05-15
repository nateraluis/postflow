from .models import ScheduledPost, ScheduledBoost, ScheduledThread
from .payload import build_payload
import pytz
import datetime
import time as time_module
from pixelfed.utils import post_pixelfed
from instagram.utils import post_instagram
from mastodon_native.utils import post_mastodon
import logging
import requests

logger = logging.getLogger("postflow")


def post_scheduled():
    """
    Processes all pending scheduled posts that are due for publishing.
    Handles both standalone posts and threaded posts.
    """
    now = datetime.datetime.now(pytz.utc)

    # Process threads first (must publish in order)
    _process_threads(now)

    # Process standalone posts (no thread)
    posts = ScheduledPost.objects.filter(
        status="pending", post_date__lte=now, thread__isnull=True
    ).order_by("post_date")

    if not posts.exists():
        logger.debug("No pending standalone posts to process")
    else:
        logger.info(f"Processing {posts.count()} pending standalone post(s)")
        for post in posts:
            _publish_post(post)

    # Process scheduled boosts
    _process_boosts(now)

    # Process auto-deletions
    _process_auto_deletes(now)


def _publish_post(post, in_reply_to_ids=None):
    """Publish a single post to all configured platforms."""
    try:
        logger.info(f"Processing post ID {post.id} scheduled for {post.post_date}")
        payload = build_payload(post)

        if post.mastodon_accounts.exists():
            post_pixelfed(post, payload, in_reply_to_id=in_reply_to_ids.get('pixelfed') if in_reply_to_ids else None)

        if post.mastodon_native_accounts.exists():
            post_mastodon(post, payload, in_reply_to_id=in_reply_to_ids.get('mastodon') if in_reply_to_ids else None)

        if post.instagram_accounts.exists():
            post_instagram(post, payload)

        post.refresh_from_db()
        logger.info(f"Post ID {post.id} completed with status: {post.status}")

    except Exception as e:
        logger.exception(f"Unexpected error processing post ID {post.id}: {str(e)}")
        post.status = "failed"
        post.save(update_fields=["status"])


def _process_threads(now):
    """Process threaded posts — publish in order with in_reply_to_id chaining."""
    threads = ScheduledThread.objects.filter(
        posts__status="pending",
        posts__post_date__lte=now,
    ).distinct()

    for thread in threads:
        thread_posts = thread.posts.filter(
            status="pending", post_date__lte=now
        ).order_by("thread_order")

        if not thread_posts.exists():
            continue

        logger.info(f"Processing thread '{thread}' with {thread_posts.count()} pending posts")

        # Track reply IDs per platform for chaining
        reply_ids = {}

        for post in thread_posts:
            payload = build_payload(post)

            try:
                # Pixelfed/Mastodon-compatible
                if post.mastodon_accounts.exists():
                    post_pixelfed(post, payload, in_reply_to_id=reply_ids.get('pixelfed'))
                    post.refresh_from_db()
                    if post.pixelfed_post_id:
                        reply_ids['pixelfed'] = post.pixelfed_post_id
                    elif post.mastodon_post_id:
                        reply_ids['pixelfed'] = post.mastodon_post_id

                # Native Mastodon
                if post.mastodon_native_accounts.exists():
                    post_mastodon(post, payload, in_reply_to_id=reply_ids.get('mastodon'))
                    post.refresh_from_db()
                    if post.mastodon_post_id:
                        reply_ids['mastodon'] = post.mastodon_post_id

                # Instagram: only post the first item in the thread
                if post.thread_order == 0 and post.instagram_accounts.exists():
                    post_instagram(post, payload)

                # Small delay between thread posts to avoid rate limits
                time_module.sleep(1)

            except Exception as e:
                logger.exception(f"Error in thread post ID {post.id}: {str(e)}")
                post.status = "failed"
                post.save(update_fields=["status"])
                break  # Stop thread on failure


def _process_boosts(now):
    """Process scheduled boosts/reblogs."""
    boosts = ScheduledBoost.objects.filter(
        status="pending", boost_date__lte=now
    )

    for boost in boosts:
        try:
            status_id = boost.status_id
            if not status_id and boost.status_url:
                # Resolve URL to ID via Mastodon search API
                account = boost.mastodon_accounts.first() or None
                native = boost.mastodon_native_accounts.first() or None
                if account:
                    try:
                        headers = {"Authorization": f"Bearer {account.access_token}"}
                        resp = requests.get(
                            f"{account.instance_url}/api/v2/search",
                            params={"q": boost.status_url, "type": "statuses", "resolve": "true", "limit": 1},
                            headers=headers, timeout=15,
                        )
                        if resp.status_code == 200:
                            statuses = resp.json().get("statuses", [])
                            if statuses:
                                status_id = statuses[0]["id"]
                                boost.status_id = status_id
                                boost.save(update_fields=["status_id"])
                                logger.info(f"Resolved boost URL to status_id {status_id}")
                    except Exception as e:
                        logger.error(f"Failed to resolve boost URL: {e}")
                elif native:
                    try:
                        from mastodon import Mastodon
                        client = Mastodon(access_token=native.access_token, api_base_url=native.instance_url)
                        results = client.search_v2(boost.status_url, result_type="statuses")
                        if results and results.get("statuses"):
                            status_id = results["statuses"][0]["id"]
                            boost.status_id = status_id
                            boost.save(update_fields=["status_id"])
                            logger.info(f"Resolved boost URL to status_id {status_id}")
                    except Exception as e:
                        logger.error(f"Failed to resolve boost URL: {e}")

            if not status_id:
                logger.warning(f"Boost {boost.id}: could not resolve status_id from URL {boost.status_url}")
                boost.status = "failed"
                boost.save(update_fields=["status"])
                continue

            # Boost on Pixelfed/Mastodon-compatible accounts
            for account in boost.mastodon_accounts.all():
                headers = {
                    "Authorization": f"Bearer {account.access_token}",
                    "Accept": "application/json",
                }
                url = f"{account.instance_url}/api/v1/statuses/{status_id}/reblog"
                resp = requests.post(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    logger.info(f"Boosted {status_id} on @{account.username}")
                else:
                    logger.error(f"Failed to boost on @{account.username}: {resp.status_code}")

            # Boost on native Mastodon accounts
            for account in boost.mastodon_native_accounts.all():
                from mastodon import Mastodon
                client = Mastodon(access_token=account.access_token, api_base_url=account.instance_url)
                client.status_reblog(status_id)
                logger.info(f"Boosted {status_id} on Mastodon @{account.username}")

            boost.status = "posted"
            boost.save(update_fields=["status"])

        except Exception as e:
            logger.exception(f"Error processing boost {boost.id}: {str(e)}")
            boost.status = "failed"
            boost.save(update_fields=["status"])


def _process_auto_deletes(now):
    """Delete posts that have passed their auto-delete TTL."""
    from django.utils.timezone import timedelta

    posts = ScheduledPost.objects.filter(
        status="posted",
        delete_after_hours__isnull=False,
    )

    for post in posts:
        ttl = timedelta(hours=post.delete_after_hours)
        if post.post_date + ttl > now:
            continue  # Not yet expired

        logger.info(f"Auto-deleting post {post.id} (TTL: {post.delete_after_hours}h)")

        # Delete on Pixelfed/Mastodon-compatible
        if post.mastodon_post_id:
            for account in post.mastodon_accounts.all():
                try:
                    headers = {"Authorization": f"Bearer {account.access_token}"}
                    url = f"{account.instance_url}/api/v1/statuses/{post.mastodon_post_id}"
                    requests.delete(url, headers=headers, timeout=15)
                    logger.info(f"Deleted post {post.mastodon_post_id} from @{account.username}")
                except Exception as e:
                    logger.error(f"Failed to delete from Pixelfed @{account.username}: {e}")

        # Delete on native Mastodon
        if post.mastodon_post_id:
            for account in post.mastodon_native_accounts.all():
                try:
                    from mastodon import Mastodon
                    client = Mastodon(access_token=account.access_token, api_base_url=account.instance_url)
                    client.status_delete(post.mastodon_post_id)
                    logger.info(f"Deleted post from Mastodon @{account.username}")
                except Exception as e:
                    logger.error(f"Failed to delete from Mastodon @{account.username}: {e}")

        # Instagram: cannot delete via API, skip silently

        # Mark as deleted
        post.status = "deleted"
        post.save(update_fields=["status"])
