import requests
import logging
import time
from django.utils.timezone import now

logger = logging.getLogger("postflow")


def _validate_instagram_caption(caption: str) -> bool:
    """
    Validates Instagram caption for common issues.
    Instagram caption limit: ~2,200 characters
    """
    if not caption:
        return True

    if len(caption) > 2200:
        logger.warning(f"Caption exceeds Instagram limit (2,200 chars). Length: {len(caption)}")
        return False

    return True


def _validate_image_url(image_url: str, timeout: int = 10) -> bool:
    """
    Validates that image URL is accessible and returns a valid image.
    Uses GET instead of HEAD to better test Instagram's ability to download.
    """
    try:
        # Use GET with stream=True to check accessibility without downloading full file
        response = requests.get(image_url, timeout=timeout, allow_redirects=True, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "image" not in content_type:
            logger.warning(f"Invalid content type for image URL: {content_type}")
            return False

        content_length = response.headers.get("content-length", 0)
        if content_length and int(content_length) > 8 * 1024 * 1024:  # 8MB limit
            logger.warning(f"Image exceeds 8MB limit. Size: {int(content_length) / 1024 / 1024:.2f}MB")
            return False

        return True
    except requests.RequestException as e:
        logger.error(f"Failed to validate image URL: {str(e)}")
        return False


def _parse_instagram_error(response) -> tuple:
    """
    Extracts error code and message from Instagram API response.
    Returns: (error_code, error_message)
    """
    try:
        error_data = response.json()
        if "error" in error_data:
            error = error_data["error"]
            if isinstance(error, dict):
                error_msg = error.get("message", str(error))
                error_code = error.get("code", "unknown")
                error_type = error.get("type", "unknown")
                return (error_code, f"{error_type} ({error_code}): {error_msg}")
            else:
                return ("unknown", str(error))
        return ("unknown", response.text[:500])  # Limit response text
    except (ValueError, KeyError):
        return ("unknown", response.text[:500])


def post_instagram(scheduled_post, retry_count=0, max_retries=2):
    """
    Publishes a scheduled post image(s) to all linked Instagram Business Accounts.
    Supports both single images and carousels (up to 10 images).
    Includes validation, error parsing, and retry logic.

    Args:
        scheduled_post: ScheduledPost instance to publish
        retry_count: Current retry attempt (internal use)
        max_retries: Maximum retry attempts for transient errors
    """
    from postflow.utils import get_s3_signed_url
    from postflow.models import Tag

    # Get all images for this post
    image_urls = []

    # Check for PostImage records (new multi-image posts)
    if scheduled_post.images.exists():
        for post_image in scheduled_post.images.all():
            image_url = get_s3_signed_url(post_image.image.name, expiration=86400)  # 24-hour expiration
            if image_url:
                image_urls.append(image_url)
    # Fallback to legacy single image field
    elif scheduled_post.image:
        image_url = get_s3_signed_url(scheduled_post.image.name, expiration=86400)
        if image_url:
            image_urls.append(image_url)

    if not image_urls:
        logger.error(f"Could not generate signed URLs for scheduled post ID {scheduled_post.id}")
        scheduled_post.status = "failed"
        scheduled_post.save(update_fields=["status"])
        return

    # Validate and combine caption + hashtags
    caption = scheduled_post.caption or ""
    hashtags = " ".join(
        tag.name
        for tag_group in scheduled_post.hashtag_groups.all()
        for tag in tag_group.tags.all()
    )
    full_caption = f"{caption}\n{hashtags}".strip() if caption or hashtags else ""

    # Validate caption length
    if not _validate_instagram_caption(full_caption):
        logger.error(f"Invalid caption for post ID {scheduled_post.id}: exceeds length limit")
        scheduled_post.status = "failed"
        scheduled_post.save(update_fields=["status"])
        return

    # Validate all image URLs are accessible
    for idx, img_url in enumerate(image_urls):
        if not _validate_image_url(img_url):
            logger.error(f"Image URL validation failed for image {idx + 1} in post ID {scheduled_post.id}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

    is_carousel = len(image_urls) > 1
    logger.info(f"Posting {'carousel with ' + str(len(image_urls)) + ' images' if is_carousel else 'single image'} to Instagram")

    for account in scheduled_post.instagram_accounts.all():
        try:
            # Check if token is expired before attempting post
            if account.expires_at and account.expires_at <= now():
                logger.error(f"Instagram token expired for @{account.username}. Cannot post.")
                continue

            logger.info(f"Posting to Instagram Business Account @{account.username}")

            # Step 1: Create media container(s)
            create_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}/media"

            if is_carousel:
                # Create child containers for each image in carousel
                child_container_ids = []

                for idx, img_url in enumerate(image_urls):
                    child_payload = {
                        "image_url": img_url,
                        "is_carousel_item": "true",
                        "access_token": account.access_token,
                    }

                    logger.debug(f"Creating carousel child container {idx + 1}/{len(image_urls)}")
                    child_response = requests.post(create_url, data=child_payload, timeout=15)

                    if child_response.status_code != 200:
                        error_msg = _parse_instagram_error(child_response)
                        logger.error(f"Failed to create child container {idx + 1}: {error_msg}")
                        scheduled_post.status = "failed"
                        scheduled_post.save(update_fields=["status"])
                        return

                    child_data = child_response.json()
                    child_id = child_data.get("id")
                    if not child_id:
                        logger.error(f"No container ID in response for child {idx + 1}")
                        scheduled_post.status = "failed"
                        scheduled_post.save(update_fields=["status"])
                        return

                    child_container_ids.append(child_id)
                    logger.debug(f"Created child container {idx + 1}: {child_id}")

                # Create parent carousel container
                carousel_payload = {
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_container_ids),
                    "caption": full_caption,
                    "access_token": account.access_token,
                }

                logger.debug(f"Creating carousel parent container with {len(child_container_ids)} children")
                media_response = requests.post(create_url, data=carousel_payload, timeout=15)
            else:
                # Single image post
                media_payload = {
                    "image_url": image_urls[0],
                    "caption": full_caption,
                    "access_token": account.access_token,
                }

                logger.debug(f"Creating single image container at {create_url}")
                media_response = requests.post(create_url, data=media_payload, timeout=15)

            # Check status before parsing
            if media_response.status_code != 200:
                error_msg = _parse_instagram_error(media_response)
                logger.error(f"Failed to create media container for @{account.username}: {error_msg}")

                # Detect if it's a transient error (5xx) and retry
                if media_response.status_code >= 500 and retry_count < max_retries:
                    logger.warning(f"Transient server error. Retrying in 2 seconds (attempt {retry_count + 1}/{max_retries})")
                    time.sleep(2)
                    return post_instagram(scheduled_post, retry_count=retry_count + 1, max_retries=max_retries)

                # Non-transient errors should mark as failed
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            try:
                media_response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                error_msg = _parse_instagram_error(media_response)
                logger.error(f"HTTP error creating container: {error_msg}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            media_data = media_response.json()
            container_id = media_data.get("id")

            if not container_id:
                logger.error(f"No container ID in Instagram response for @{account.username}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            logger.debug(f"Created media container: {container_id}")

            # Step 2: Publish the container (with retry logic for media availability)
            publish_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}/media_publish"
            publish_payload = {
                "creation_id": container_id,
                "access_token": account.access_token,
            }

            # Retry publishing up to 3 times if media is not available
            max_publish_retries = 3
            publish_attempt = 0

            while publish_attempt < max_publish_retries:
                logger.debug(f"Publishing media container (attempt {publish_attempt + 1}/{max_publish_retries}) at {publish_url}")
                publish_response = requests.post(publish_url, data=publish_payload, timeout=15)

                # Check publish response
                if publish_response.status_code == 200:
                    # Success - extract media ID
                    try:
                        publish_data = publish_response.json()
                        ig_media_id = publish_data.get("id")

                        if ig_media_id:
                            logger.info(f"Successfully posted to Instagram @{account.username}, media ID: {ig_media_id}")
                            # Mark as posted and store media ID
                            scheduled_post.status = "posted"
                            scheduled_post.instagram_media_id = ig_media_id
                            scheduled_post.save(update_fields=["status", "instagram_media_id"])
                            # Add small delay between multiple accounts to avoid rate limiting
                            time.sleep(1)
                            break  # Exit the retry loop on success
                        else:
                            logger.error(f"No media ID returned from Instagram for @{account.username}")
                            scheduled_post.status = "failed"
                            scheduled_post.save(update_fields=["status"])
                            return
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing publish response: {str(e)}")
                        scheduled_post.status = "failed"
                        scheduled_post.save(update_fields=["status"])
                        return

                elif publish_response.status_code != 200:
                    error_code, error_msg = _parse_instagram_error(publish_response)
                    logger.error(f"Failed to publish media for @{account.username}: {error_msg}")

                    # Special handling for error 9007: Media ID is not available (media still processing)
                    # error_code is a string, so compare as string
                    if str(error_code) == "9007" and publish_attempt < max_publish_retries - 1:
                        wait_time = 2 * (publish_attempt + 1)  # 2s, 4s, 6s
                        logger.warning(f"Media not ready yet (error 9007). Retrying in {wait_time}s (attempt {publish_attempt + 1}/{max_publish_retries})")
                        time.sleep(wait_time)
                        publish_attempt += 1
                        continue

                    # Retry on transient errors (5xx)
                    if publish_response.status_code >= 500 and publish_attempt < max_publish_retries - 1:
                        wait_time = 2 * (publish_attempt + 1)
                        logger.warning(f"Transient server error on publish. Retrying in {wait_time}s (attempt {publish_attempt + 1}/{max_publish_retries})")
                        time.sleep(wait_time)
                        publish_attempt += 1
                        continue

                    # Non-retriable errors - mark as failed
                    logger.error(f"Non-retriable error. Giving up on post for @{account.username}")
                    scheduled_post.status = "failed"
                    scheduled_post.save(update_fields=["status"])
                    return

                # Increment attempt counter if we get here without break or return (should not reach here normally)
                publish_attempt += 1

            # If we've exhausted retries, mark as failed
            if publish_attempt >= max_publish_retries:
                logger.error(f"Failed to publish media for @{account.username} after {max_publish_retries} attempts")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

        except requests.exceptions.Timeout:
            logger.error(f"Timeout posting to Instagram @{account.username}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error posting to Instagram @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

        except requests.RequestException as e:
            logger.error(f"Request exception posting to Instagram @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

        except Exception as e:
            logger.exception(f"Unexpected error posting to Instagram @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return
