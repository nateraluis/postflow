"""
Background tasks for Mastodon analytics using Django 6.0 tasks framework.

These tasks run hourly to fetch engagement metrics from connected Mastodon accounts.
"""
import logging
from time import sleep
from datetime import timedelta
from django.utils import timezone
from django_tasks import task
from mastodon_native.models import MastodonAccount
from .fetcher import MastodonAnalyticsFetcher

logger = logging.getLogger('postflow')


@task(queue_name='default', priority=5)
def fetch_all_mastodon_engagement():
    """
    Background task to fetch engagement for all Mastodon accounts.

    Runs hourly via django-tasks scheduler. Fetches favourites, replies, and reblogs
    for recent posts (last 24 hours) from all connected Mastodon accounts.

    Returns:
        dict: Aggregated statistics including:
            - accounts_processed: Number of accounts fetched
            - posts_processed: Total posts processed
            - total_new_favourites: New favourites found
            - total_new_replies: New replies found
            - total_new_reblogs: New reblogs found
            - errors: Number of errors encountered
    """
    logger.info("Starting hourly Mastodon engagement fetch")

    # Get Mastodon accounts (from mastodon_native table)
    mastodon_accounts = MastodonAccount.objects.all()

    logger.info(f"Found {mastodon_accounts.count()} Mastodon accounts to process")

    total_stats = {
        'accounts_processed': 0,
        'posts_processed': 0,
        'total_new_favourites': 0,
        'total_new_replies': 0,
        'total_new_reblogs': 0,
        'errors': 0,
    }

    for account in mastodon_accounts:
        try:
            logger.info(f"Fetching engagement for @{account.username} on {account.instance_url}")

            # Update last sync timestamp at start
            now = timezone.now()
            account.last_engagement_sync_at = now
            account.next_engagement_sync_at = now + timedelta(hours=2)  # Next sync in 2 hours
            account.save(update_fields=['last_engagement_sync_at', 'next_engagement_sync_at'])

            fetcher = MastodonAnalyticsFetcher(account)

            # Fetch engagement for recent posts (last 24 hours, max 30 posts)
            stats = fetcher.fetch_all_engagement(limit_posts=30)

            # Aggregate stats
            total_stats['accounts_processed'] += 1
            total_stats['posts_processed'] += stats.get('posts_processed', 0)
            total_stats['total_new_favourites'] += stats.get('total_favourites', 0)
            total_stats['total_new_replies'] += stats.get('total_replies', 0)
            total_stats['total_new_reblogs'] += stats.get('total_reblogs', 0)

            logger.info(
                f"Processed {stats.get('posts_processed', 0)} posts for @{account.username}: "
                f"{stats.get('total_favourites', 0)} favourites, "
                f"{stats.get('total_replies', 0)} replies, "
                f"{stats.get('total_reblogs', 0)} reblogs"
            )

            # Rate limiting between accounts (don't overwhelm the API)
            sleep(5)

        except Exception as e:
            logger.error(f"Error fetching engagement for {account.username}: {e}", exc_info=True)
            total_stats['errors'] += 1

    logger.info(
        f"Hourly engagement fetch complete: "
        f"{total_stats['accounts_processed']} accounts, "
        f"{total_stats['posts_processed']} posts, "
        f"{total_stats['total_new_favourites']} favourites, "
        f"{total_stats['total_new_replies']} replies, "
        f"{total_stats['total_new_reblogs']} reblogs, "
        f"{total_stats['errors']} errors"
    )

    return total_stats


@task(queue_name='default', priority=5)
def sync_all_mastodon_posts():
    """
    Background task to sync posts from all Mastodon accounts.

    Fetches recent posts from Mastodon and creates MastodonPost records.
    This should run less frequently than engagement fetching (e.g., daily).

    Returns:
        dict: Statistics including:
            - accounts_processed: Number of accounts synced
            - posts_created: New posts created
            - posts_updated: Existing posts updated
            - errors: Number of errors encountered
    """
    logger.info("Starting Mastodon posts sync")

    mastodon_accounts = MastodonAccount.objects.all()

    logger.info(f"Found {mastodon_accounts.count()} Mastodon accounts to sync")

    total_stats = {
        'accounts_processed': 0,
        'posts_created': 0,
        'posts_updated': 0,
        'errors': 0,
    }

    for account in mastodon_accounts:
        try:
            logger.info(f"Syncing posts for @{account.username} on {account.instance_url}")

            # Update last sync timestamp at start
            now = timezone.now()
            account.last_posts_sync_at = now
            account.next_posts_sync_at = now + timedelta(hours=1)  # Next sync in 1 hour
            account.save(update_fields=['last_posts_sync_at', 'next_posts_sync_at'])

            fetcher = MastodonAnalyticsFetcher(account)

            # Sync last 50 posts
            created, updated = fetcher.sync_account_posts(limit=50)

            total_stats['accounts_processed'] += 1
            total_stats['posts_created'] += created
            total_stats['posts_updated'] += updated

            logger.info(
                f"Synced posts for @{account.username}: "
                f"{created} created, {updated} updated"
            )

            # Rate limiting between accounts
            sleep(5)

        except Exception as e:
            logger.error(f"Error syncing posts for {account.username}: {e}", exc_info=True)
            total_stats['errors'] += 1

    logger.info(
        f"Posts sync complete: "
        f"{total_stats['accounts_processed']} accounts, "
        f"{total_stats['posts_created']} created, "
        f"{total_stats['posts_updated']} updated, "
        f"{total_stats['errors']} errors"
    )

    return total_stats


@task(queue_name='default', priority=10)
def fetch_account_engagement(account_id: int, limit_posts: int = 50):
    """
    Background task to fetch engagement for a specific Mastodon account.

    This task is triggered manually by users from the dashboard to immediately
    fetch engagement metrics for their posts without waiting for the hourly task.

    Args:
        account_id: MastodonAccount ID to fetch engagement for
        limit_posts: Number of recent posts to process (default 50)

    Returns:
        dict: Statistics including posts_processed, favourites, replies, reblogs
    """
    logger.info(f"Starting manual engagement fetch for account {account_id}")

    try:
        account = MastodonAccount.objects.get(pk=account_id)

        logger.info(f"Fetching engagement for @{account.username} on {account.instance_url}")

        fetcher = MastodonAnalyticsFetcher(account)
        stats = fetcher.fetch_all_engagement(limit_posts=limit_posts)

        logger.info(
            f"Manual fetch complete for @{account.username}: "
            f"{stats.get('posts_processed', 0)} posts, "
            f"{stats.get('total_favourites', 0)} favourites, "
            f"{stats.get('total_replies', 0)} replies, "
            f"{stats.get('total_reblogs', 0)} reblogs"
        )

        return stats

    except MastodonAccount.DoesNotExist:
        logger.error(f"Mastodon account {account_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error fetching engagement for account {account_id}: {e}", exc_info=True)
        raise
