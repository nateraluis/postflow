import logging
from mastodon import Mastodon

logger = logging.getLogger("postflow")


def post_mastodon(scheduled_post, payload=None, in_reply_to_id=None):
    """
    Posts to Mastodon accounts using Mastodon.py library with support for multiple images.
    Accepts an optional PostPayload for centralized caption/hashtag assembly.
    """
    # Get all images for this post
    image_files = scheduled_post.get_all_images()
    if not image_files:
        logger.error(f"Could not get image files for scheduled post ID {scheduled_post.id}")
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

            # Upload all images and collect media IDs
            media_ids = []
            logger.info(f"Uploading {len(image_files)} image(s) to Mastodon @{account.username} on {account.instance_url}")

            for idx, image_file in enumerate(image_files):
                image_file.seek(0)  # Reset file pointer to beginning

                # Get alt text (description) if available
                description = None
                if payload:
                    alt_text = payload.get_alt_text(idx)
                    if alt_text:
                        description = alt_text

                media = mastodon.media_post(
                    image_file,
                    mime_type="image/jpeg",
                    description=description,
                )
                media_ids.append(media["id"])
                logger.info(f"Uploaded image {idx + 1}/{len(image_files)} - Media ID: {media['id']}")

            # Build status text
            if payload:
                status_text = payload.get_full_caption("mastodon")
                # Append user tag mentions for Mastodon
                mentions = []
                for ut in payload.user_tags:
                    if ut.get('platform') in ('mastodon', 'pixelfed') and ut.get('username'):
                        mentions.append(ut['username'])
                if mentions:
                    mention_str = " ".join(mentions)
                    status_text = f"{status_text}\n{mention_str}".strip()
            else:
                # Fallback: build from scheduled_post directly
                hashtags = " ".join(
                    tag.hashtag
                    for tag_group in scheduled_post.hashtag_groups.all()
                    for tag in tag_group.tags.all()
                )
                status_text = scheduled_post.caption or ""
                if hashtags:
                    status_text = f"{status_text}\n{hashtags}".strip()

            # Post status with all media IDs
            visibility = payload.visibility if payload else "public"
            spoiler = payload.spoiler_text if payload else ""
            language = payload.language if payload else None

            logger.info(f"Posting status to Mastodon @{account.username} with {len(media_ids)} image(s), visibility={visibility}")
            post_kwargs = {
                "status": status_text,
                "media_ids": media_ids,
                "visibility": visibility,
            }
            if spoiler:
                post_kwargs["spoiler_text"] = spoiler
                post_kwargs["sensitive"] = True
            if language:
                post_kwargs["language"] = language
            if in_reply_to_id:
                post_kwargs["in_reply_to_id"] = in_reply_to_id

            # Add poll if present
            if payload and payload.poll_options and len(payload.poll_options) >= 2:
                post_response = mastodon.make_poll(
                    payload.poll_options,
                    expires_in=payload.poll_expires_in or 86400,
                    multiple=payload.poll_multiple,
                    hide_totals=payload.poll_hide_totals,
                )
                post_kwargs["poll"] = post_response

            post_response = mastodon.status_post(**post_kwargs)

            # Update ScheduledPost with post ID and status
            scheduled_post.mastodon_post_id = post_response.get("id")
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["mastodon_post_id", "status"])
            logger.info(f"Successfully posted to Mastodon @{account.username}, post ID: {scheduled_post.mastodon_post_id}")

        except Exception as e:
            logger.error(f"Error posting to Mastodon @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
