import requests
import logging

logger = logging.getLogger("postflow")


def post_pixelfed(scheduled_post):
    """
    Posts to Pixelfed/Mastodon accounts with support for multiple images.
    Uses logging for visibility.
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
            hashtags = " ".join(
                tag.name
                for tag_group in scheduled_post.hashtag_groups.all()
                for tag in tag_group.tags.all()
            )
            status_text = scheduled_post.caption or ""
            if hashtags:
                status_text = f"{status_text}\n{hashtags}".strip()

            data = {
                "status": status_text,
                "visibility": "public",
            }

            # Prepare multiple files for upload
            # Reset file pointers for all images
            for img in image_files:
                img.seek(0)

            # Build files list for multiple images
            files = []
            for idx, image_file in enumerate(image_files):
                files.append(("file[]", (f"image{idx}.jpg", image_file, "image/jpeg")))

            logger.info(f"Posting {len(image_files)} image(s) to Pixelfed account @{account.username} on {account.instance_url}")
            pixelfed_api_status = account.instance_url + "/api/v1.1/status/create"

            response = requests.post(
                pixelfed_api_status,
                headers=headers,
                files=files,
                data=data,
                timeout=30  # Increased timeout for multiple images
            )
            response.raise_for_status()
            post_response = response.json()

            # Update ScheduledPost with post ID and status
            scheduled_post.mastodon_post_id = post_response.get("id")
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["mastodon_post_id", "status"])
            logger.info(f"Successfully posted to Pixelfed @{account.username}, post ID: {scheduled_post.mastodon_post_id}")

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
