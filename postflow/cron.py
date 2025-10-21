from .models import ScheduledPost
import pytz
import datetime
from .utils import post_pixelfed, post_instagram
import logging

logger = logging.getLogger("postflow")


def post_scheduled():
    """
    Processes all pending scheduled posts that are due for publishing.
    Attempts to post to both Pixelfed and Instagram accounts.
    """
    # Get the current UTC date time
    now = datetime.datetime.now(pytz.utc)

    # Get all scheduled posts with status pending and postdate <= now
    posts = ScheduledPost.objects.filter(status="pending", post_date__lte=now).order_by("post_date")

    if not posts.exists():
        logger.debug("No pending posts to process")
        return

    logger.info(f"Processing {posts.count()} pending post(s)")

    for post in posts:
        try:
            logger.info(f"Processing post ID {post.id} scheduled for {post.post_date}")

            # Post to Pixelfed/Mastodon
            if post.mastodon_accounts.exists():
                logger.info(f"Posting to {post.mastodon_accounts.count()} Mastodon account(s)")
                post_pixelfed(post)
            else:
                logger.debug(f"No Mastodon accounts configured for post ID {post.id}")

            # Post to Instagram
            if post.instagram_accounts.exists():
                logger.info(f"Posting to {post.instagram_accounts.count()} Instagram account(s)")
                post_instagram(post)
            else:
                logger.debug(f"No Instagram accounts configured for post ID {post.id}")

            # Log final status
            post.refresh_from_db()
            logger.info(f"Post ID {post.id} completed with status: {post.status}")

        except Exception as e:
            logger.exception(f"Unexpected error processing post ID {post.id}: {str(e)}")
            # Ensure post is marked as failed if something goes wrong
            post.status = "failed"
            post.save(update_fields=["status"])

    logger.info(f"Finished processing {posts.count()} post(s)")
