"""
Background tasks for Pixelfed analytics using Django 6.0 tasks framework.

These tasks run hourly to fetch engagement metrics from connected Pixelfed accounts.
"""
import logging
from time import sleep
from django_tasks import task
from pixelfed.models import MastodonAccount
from .fetcher import PixelfedAnalyticsFetcher

logger = logging.getLogger('postflow')


@task(queue_name='default', priority=5)
def fetch_all_pixelfed_engagement():
    """
    Background task to fetch engagement for all Pixelfed accounts.

    Runs hourly via django-tasks scheduler. Fetches likes, comments, and shares
    for recent posts (last 24 hours) from all connected Pixelfed accounts.

    Returns:
        dict: Aggregated statistics including:
            - accounts_processed: Number of accounts fetched
            - posts_processed: Total posts processed
            - total_new_likes: New likes found
            - total_new_comments: New comments found
            - total_new_shares: New shares found
            - errors: Number of errors encountered
    """
    logger.info("Starting hourly Pixelfed engagement fetch")

    # Get Pixelfed accounts (filter by instance_url containing 'pixelfed')
    pixelfed_accounts = MastodonAccount.objects.filter(
        instance_url__icontains='pixelfed'
    )

    logger.info(f"Found {pixelfed_accounts.count()} Pixelfed accounts to process")

    total_stats = {
        'accounts_processed': 0,
        'posts_processed': 0,
        'total_new_likes': 0,
        'total_new_comments': 0,
        'total_new_shares': 0,
        'errors': 0,
    }

    for account in pixelfed_accounts:
        try:
            logger.info(f"Fetching engagement for @{account.username} on {account.instance_url}")
            fetcher = PixelfedAnalyticsFetcher(account)

            # Fetch engagement for recent posts (last 24 hours, max 30 posts)
            stats = fetcher.fetch_all_engagement(limit_posts=30)

            # Aggregate stats
            total_stats['accounts_processed'] += 1
            total_stats['posts_processed'] += stats.get('posts_processed', 0)
            total_stats['total_new_likes'] += stats.get('total_likes', 0)
            total_stats['total_new_comments'] += stats.get('total_comments', 0)
            total_stats['total_new_shares'] += stats.get('total_shares', 0)

            logger.info(
                f"Processed {stats.get('posts_processed', 0)} posts for @{account.username}: "
                f"{stats.get('total_likes', 0)} likes, "
                f"{stats.get('total_comments', 0)} comments, "
                f"{stats.get('total_shares', 0)} shares"
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
        f"{total_stats['total_new_likes']} likes, "
        f"{total_stats['total_new_comments']} comments, "
        f"{total_stats['total_new_shares']} shares, "
        f"{total_stats['errors']} errors"
    )

    return total_stats


@task(queue_name='default', priority=5)
def sync_all_pixelfed_posts():
    """
    Background task to sync posts from all Pixelfed accounts.

    Fetches recent posts from Pixelfed and creates PixelfedPost records.
    This should run less frequently than engagement fetching (e.g., daily).

    Returns:
        dict: Statistics including:
            - accounts_processed: Number of accounts synced
            - posts_created: New posts created
            - posts_updated: Existing posts updated
            - errors: Number of errors encountered
    """
    logger.info("Starting Pixelfed posts sync")

    pixelfed_accounts = MastodonAccount.objects.filter(
        instance_url__icontains='pixelfed'
    )

    logger.info(f"Found {pixelfed_accounts.count()} Pixelfed accounts to sync")

    total_stats = {
        'accounts_processed': 0,
        'posts_created': 0,
        'posts_updated': 0,
        'errors': 0,
    }

    for account in pixelfed_accounts:
        try:
            logger.info(f"Syncing posts for @{account.username} on {account.instance_url}")
            fetcher = PixelfedAnalyticsFetcher(account)

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
    Background task to fetch engagement for a specific Pixelfed account.

    This task is triggered manually by users from the dashboard to immediately
    fetch engagement metrics for their posts without waiting for the hourly task.

    Args:
        account_id: MastodonAccount ID to fetch engagement for
        limit_posts: Number of recent posts to process (default 50)

    Returns:
        dict: Statistics including posts_processed, likes, comments, shares
    """
    logger.info(f"Starting manual engagement fetch for account {account_id}")

    try:
        account = MastodonAccount.objects.get(
            pk=account_id,
            instance_url__icontains='pixelfed'
        )

        logger.info(f"Fetching engagement for @{account.username} on {account.instance_url}")

        fetcher = PixelfedAnalyticsFetcher(account)
        stats = fetcher.fetch_all_engagement(limit_posts=limit_posts)

        logger.info(
            f"Manual fetch complete for @{account.username}: "
            f"{stats.get('posts_processed', 0)} posts, "
            f"{stats.get('total_likes', 0)} likes, "
            f"{stats.get('total_comments', 0)} comments, "
            f"{stats.get('total_shares', 0)} shares"
        )

        return stats

    except MastodonAccount.DoesNotExist:
        logger.error(f"Pixelfed account {account_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error fetching engagement for account {account_id}: {e}", exc_info=True)
        raise
