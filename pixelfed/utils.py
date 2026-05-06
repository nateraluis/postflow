import requests
import logging

logger = logging.getLogger("postflow")


def post_pixelfed(scheduled_post, payload=None, in_reply_to_id=None):
    """
    Posts to Pixelfed/Mastodon accounts with support for multiple images.
    Uses Mastodon-compatible API with media upload then status post.
    Accepts an optional PostPayload for centralized caption/hashtag assembly.
    """
    # Get all images for this post
    image_files = scheduled_post.get_all_images()
    if not image_files:
        logger.error(f"Could not get image files for scheduled post ID {scheduled_post.id}")
        return

    for account in scheduled_post.mastodon_accounts.all():
        try:
            headers = {
                "Authorization": f"Bearer {account.access_token}",
                "Accept": "application/json",
            }

            logger.info(f"Posting {len(image_files)} image(s) to Pixelfed account @{account.username} on {account.instance_url}")

            # Step 1: Upload media files and collect media IDs
            media_ids = []
            media_upload_url = account.instance_url + "/api/v1/media"

            for idx, image_file in enumerate(image_files):
                image_file.seek(0)  # Reset file pointer

                files = {"file": (f"image{idx}.jpg", image_file, "image/jpeg")}

                # Add alt text (description) if available
                data = {}
                if payload:
                    alt_text = payload.get_alt_text(idx)
                    if alt_text:
                        data["description"] = alt_text

                logger.debug(f"Uploading image {idx + 1}/{len(image_files)} to Pixelfed")
                media_response = requests.post(
                    media_upload_url,
                    headers=headers,
                    files=files,
                    data=data if data else None,
                    timeout=30
                )
                media_response.raise_for_status()
                media_data = media_response.json()
                media_id = media_data.get("id")

                if not media_id:
                    logger.error(f"No media ID returned for image {idx + 1}")
                    scheduled_post.status = "failed"
                    scheduled_post.save(update_fields=["status"])
                    return

                media_ids.append(media_id)
                logger.debug(f"Uploaded image {idx + 1}/{len(image_files)} - Media ID: {media_id}")

            # Step 2: Build status text
            if payload:
                status_text = payload.get_full_caption("pixelfed")
                # Append user tag mentions for Mastodon/Pixelfed
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

            status_url = account.instance_url + "/api/v1/statuses"
            status_data = {
                "status": status_text,
                "visibility": payload.visibility if payload else "public",
                "media_ids[]": media_ids,
            }
            if payload and payload.spoiler_text:
                status_data["spoiler_text"] = payload.spoiler_text
                status_data["sensitive"] = "true"
            if payload and payload.language:
                status_data["language"] = payload.language
            if in_reply_to_id:
                status_data["in_reply_to_id"] = in_reply_to_id

            # Build poll params as list of tuples for repeated form fields
            post_data = list(status_data.items())
            if payload and payload.poll_options and len(payload.poll_options) >= 2:
                for opt in payload.poll_options:
                    post_data.append(("poll[options][]", opt))
                post_data.append(("poll[expires_in]", str(payload.poll_expires_in or 86400)))
                if payload.poll_multiple:
                    post_data.append(("poll[multiple]", "true"))
                if payload.poll_hide_totals:
                    post_data.append(("poll[hide_totals]", "true"))

            logger.debug(f"Creating status with {len(media_ids)} media attachment(s)")
            response = requests.post(
                status_url,
                headers=headers,
                data=post_data,
                timeout=15
            )
            response.raise_for_status()
            post_response = response.json()

            # Update ScheduledPost with post ID and status
            post_id = post_response.get("id")

            # Check if this is actually a Pixelfed instance (not just Mastodon-compatible)
            is_pixelfed = "pixelfed" in account.instance_url.lower()

            if is_pixelfed:
                scheduled_post.pixelfed_post_id = post_id
                scheduled_post.mastodon_post_id = post_id
                scheduled_post.status = "posted"
                scheduled_post.save(update_fields=["mastodon_post_id", "pixelfed_post_id", "status"])
                logger.info(f"Successfully posted to Pixelfed @{account.username}, post ID: {post_id}")
            else:
                scheduled_post.mastodon_post_id = post_id
                scheduled_post.status = "posted"
                scheduled_post.save(update_fields=["mastodon_post_id", "status"])
                logger.info(f"Successfully posted to Mastodon-compatible instance @{account.username}, post ID: {post_id}")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout posting to Pixelfed @{account.username}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error posting to Pixelfed @{account.username}: {e.response.status_code}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
        except requests.RequestException as e:
            logger.error(f"Request failed posting to Pixelfed @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
