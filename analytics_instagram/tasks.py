"""
Background tasks for Instagram analytics using Django 6.0 tasks framework.

These tasks run periodically to fetch engagement metrics from connected Instagram Business accounts.
Note: Instagram has strict rate limits (200 calls/hour), so we process fewer posts per account.
"""
import logging
from time import sleep
from datetime import timedelta
from django.utils import timezone
from django_tasks import task
from instagram.models import InstagramBusinessAccount
from .fetcher import InstagramAnalyticsFetcher

logger = logging.getLogger('postflow')


@task(queue_name='default', priority=5)
def fetch_all_instagram_insights():
    """
    Background task to fetch insights for all Instagram Business accounts.

    Runs every 6 hours via scheduler. Fetches insights (engagement, reach, impressions, etc.)
    and comments for recent posts from all connected Instagram Business accounts.

    Note: Due to rate limits (200 calls/hour), we process fewer posts (max 30 per account).

    Returns:
        dict: Aggregated statistics including:
            - accounts_processed: Number of accounts fetched
            - posts_processed: Total posts processed
            - insights_fetched: Number of posts with insights updated
            - comments_fetched: Number of new comments found
            - errors: Number of errors encountered
    """
    logger.info("Starting Instagram insights fetch")

    # Get all Instagram Business accounts
    instagram_accounts = InstagramBusinessAccount.objects.all()

    logger.info(f"Found {instagram_accounts.count()} Instagram Business accounts to process")

    total_stats = {
        'accounts_processed': 0,
        'posts_processed': 0,
        'insights_fetched': 0,
        'comments_fetched': 0,
        'errors': 0,
    }

    for account in instagram_accounts:
        try:
            logger.info(f"Fetching insights for @{account.username}")

            # Update last sync timestamp at start
            now = timezone.now()
            account.last_insights_sync_at = now
            account.next_insights_sync_at = now + timedelta(hours=2)  # Next sync in 2 hours
            account.save(update_fields=['last_insights_sync_at', 'next_insights_sync_at'])

            fetcher = InstagramAnalyticsFetcher(account)

            # Fetch insights for recent posts (max 30 to manage rate limits)
            stats = fetcher.fetch_all_insights(limit_posts=30)

            # Aggregate stats
            total_stats['accounts_processed'] += 1
            total_stats['posts_processed'] += stats.get('posts_processed', 0)
            total_stats['insights_fetched'] += stats.get('insights_fetched', 0)
            total_stats['comments_fetched'] += stats.get('comments_fetched', 0)

            logger.info(
                f"Processed {stats.get('posts_processed', 0)} posts for @{account.username}: "
                f"{stats.get('insights_fetched', 0)} insights, "
                f"{stats.get('comments_fetched', 0)} comments"
            )

            # Rate limiting between accounts (Instagram is strict: 200 calls/hour)
            # Wait 10 seconds between accounts to be safe
            sleep(10)

        except Exception as e:
            logger.error(f"Error fetching insights for {account.username}: {e}", exc_info=True)
            total_stats['errors'] += 1

    logger.info(
        f"Instagram insights fetch complete: "
        f"{total_stats['accounts_processed']} accounts, "
        f"{total_stats['posts_processed']} posts, "
        f"{total_stats['insights_fetched']} insights, "
        f"{total_stats['comments_fetched']} comments, "
        f"{total_stats['errors']} errors"
    )

    return total_stats


@task(queue_name='default', priority=5)
def sync_all_instagram_posts():
    """
    Background task to sync posts from all Instagram Business accounts.

    Fetches recent posts from Instagram and creates InstagramPost records.
    This should run less frequently than insights fetching (e.g., daily).

    Returns:
        dict: Statistics including:
            - accounts_processed: Number of accounts synced
            - posts_created: New posts created
            - posts_updated: Existing posts updated
            - errors: Number of errors encountered
    """
    logger.info("Starting Instagram posts sync")

    instagram_accounts = InstagramBusinessAccount.objects.all()

    logger.info(f"Found {instagram_accounts.count()} Instagram Business accounts to sync")

    total_stats = {
        'accounts_processed': 0,
        'posts_created': 0,
        'posts_updated': 0,
        'errors': 0,
    }

    for account in instagram_accounts:
        try:
            logger.info(f"Syncing posts for @{account.username}")

            # Update last sync timestamp at start
            now = timezone.now()
            account.last_posts_sync_at = now
            account.next_posts_sync_at = now + timedelta(hours=1)  # Next sync in 1 hour
            account.save(update_fields=['last_posts_sync_at', 'next_posts_sync_at'])

            fetcher = InstagramAnalyticsFetcher(account)

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
            sleep(10)

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
def fetch_account_insights(account_id: int, limit_posts: int = 50):
    """
    Background task to fetch insights for a specific Instagram Business account.

    This task is triggered manually by users from the dashboard to immediately
    fetch insights without waiting for the scheduled task.

    Args:
        account_id: InstagramBusinessAccount ID to fetch insights for
        limit_posts: Number of recent posts to process (default 50)

    Returns:
        dict: Statistics including posts_processed, insights_fetched, comments_fetched
    """
    logger.info(f"Starting manual insights fetch for account {account_id}")

    try:
        account = InstagramBusinessAccount.objects.get(pk=account_id)

        logger.info(f"Fetching insights for @{account.username}")

        # Update last sync timestamp at start (manual fetch)
        now = timezone.now()
        account.last_insights_sync_at = now
        account.next_insights_sync_at = now + timedelta(hours=2)  # Next auto-sync in 2 hours
        account.save(update_fields=['last_insights_sync_at', 'next_insights_sync_at'])

        fetcher = InstagramAnalyticsFetcher(account)
        stats = fetcher.fetch_all_insights(limit_posts=limit_posts)

        logger.info(
            f"Manual fetch complete for @{account.username}: "
            f"{stats.get('posts_processed', 0)} posts, "
            f"{stats.get('insights_fetched', 0)} insights, "
            f"{stats.get('comments_fetched', 0)} comments"
        )

        return stats

    except InstagramBusinessAccount.DoesNotExist:
        logger.error(f"Instagram Business account {account_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error fetching insights for account {account_id}: {e}", exc_info=True)
        raise
