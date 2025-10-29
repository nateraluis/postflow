import logging
from mastodon import Mastodon

logger = logging.getLogger("postflow")


def post_mastodon(scheduled_post):
    """
    Posts to Mastodon accounts using Mastodon.py library.
    Handles image upload and status creation.
    """
    image_file = scheduled_post.get_image_file()
    if not image_file:
        logger.error(f"Could not get image file for scheduled post ID {scheduled_post.id}")
        scheduled_post.status = "failed"
        scheduled_post.save(update_fields=["status"])
        return

    for account in scheduled_post.mastodon_native_accounts.all():
        try:
            # Initialize Mastodon client
            mastodon = Mastodon(
                access_token=account.access_token,
                api_base_url=account.instance_url,
            )

            # Upload image and get media object
            logger.info(f"Uploading image to Mastodon @{account.username} on {account.instance_url}")
            image_file.seek(0)  # Reset file pointer to beginning
            media = mastodon.media_post(image_file, mime_type="image/jpeg")

            # Prepare status text with hashtags
            hashtags = " ".join(
                tag.name
                for tag_group in scheduled_post.hashtag_groups.all()
                for tag in tag_group.tags.all()
            )
            status_text = scheduled_post.caption or ""
            if hashtags:
                status_text = f"{status_text}\n{hashtags}".strip()

            # Post status
            logger.info(f"Posting status to Mastodon @{account.username}")
            post_response = mastodon.status_post(
                status=status_text,
                media_ids=[media["id"]],
                visibility="public",
            )

            # Update ScheduledPost with post ID and status
            scheduled_post.mastodon_post_id = post_response.get("id")
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["mastodon_post_id", "status"])
            logger.info(f"Successfully posted to Mastodon @{account.username}, post ID: {scheduled_post.mastodon_post_id}")

        except Exception as e:
            logger.error(f"Error posting to Mastodon @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
