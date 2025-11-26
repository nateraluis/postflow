import requests
import logging

logger = logging.getLogger("postflow")


def post_pixelfed(scheduled_post):
    """
    Posts to Pixelfed/Mastodon accounts with support for multiple images.
    Uses Mastodon-compatible API with media upload then status post.
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

                logger.debug(f"Uploading image {idx + 1}/{len(image_files)} to Pixelfed")
                media_response = requests.post(
                    media_upload_url,
                    headers=headers,
                    files=files,
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

            # Step 2: Create status with all media IDs
            hashtags = " ".join(
                tag.name
                for tag_group in scheduled_post.hashtag_groups.all()
                for tag in tag_group.tags.all()
            )
            status_text = scheduled_post.caption or ""
            if hashtags:
                status_text = f"{status_text}\n{hashtags}".strip()

            status_url = account.instance_url + "/api/v1/statuses"
            status_data = {
                "status": status_text,
                "visibility": "public",
                "media_ids[]": media_ids,
            }

            logger.debug(f"Creating status with {len(media_ids)} media attachment(s)")
            response = requests.post(
                status_url,
                headers=headers,
                data=status_data,
                timeout=15
            )
            response.raise_for_status()
            post_response = response.json()

            # Update ScheduledPost with post ID and status
            post_id = post_response.get("id")
            scheduled_post.mastodon_post_id = post_id
            scheduled_post.pixelfed_post_id = post_id  # Also set for analytics
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["mastodon_post_id", "pixelfed_post_id", "status"])
            logger.info(f"Successfully posted to Pixelfed @{account.username}, post ID: {post_id}")

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
