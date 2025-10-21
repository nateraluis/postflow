from django.conf import settings
from django.utils.timezone import now
import boto3
import requests
import logging
import time

logger = logging.getLogger("postflow")


def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.MEDIA_ACCESS_KEY_ID,
        aws_secret_access_key=settings.MEDIA_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


def get_s3_signed_url(file_path, expiration=3600):
    """
    Generates a secure, temporary signed URL for private S3 media files.
    - file_path: Path to the file in the S3 bucket (e.g., "scheduled_posts/user_1_1714000000.png")
    - expiration: Time (in seconds) before the URL expires (default: 1 hour)
    """
    if settings.DEBUG:
        return f"{settings.MEDIA_URL}{file_path}"

    s3_client = _get_s3_client()

    bucket_name = settings.AWS_STORAGE_MEDIA_BUCKET_NAME

    try:
        signed_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": file_path},
            ExpiresIn=expiration,
        )
        return signed_url
    except Exception as e:
        return None


def upload_to_s3(file, file_path):
    """
    Uploads a file to S3 manually using boto3 instead of default_storage.
    Ensures correct ACL and permissions for private storage.
    """
    if settings.DEBUG:
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        saved_path = default_storage.save(file_path, ContentFile(file.read()))
        return f"{saved_path}"
    s3_client = _get_s3_client()

    try:
        s3_client.upload_fileobj(
            file,  # File object
            settings.AWS_STORAGE_MEDIA_BUCKET_NAME,  # Bucket name
            file_path,  # File path in S3
            ExtraArgs={"ACL": "private", "ContentType": file.content_type},  # Ensure private access
        )
        return file_path  # Return the file path saved in S3
    except Exception as e:
        print(f"❌ Error uploading to S3: {e}. File: {file_path}, Bucket: {settings.AWS_STORAGE_MEDIA_BUCKET_NAME}")
        return None


def post_pixelfed(scheduled_post):
    """
    Posts to Pixelfed/Mastodon accounts. Uses logging for visibility.
    """
    image_file = scheduled_post.get_image_file()
    if not image_file:
        logger.error(f"Could not get image file for scheduled post ID {scheduled_post.id}")
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
            files = {"file": ("image.jpg", image_file, "image/jpeg")}

            logger.info(f"Posting to Pixelfed account @{account.username} on {account.instance_url}")
            pixelfed_api_status = account.instance_url + "/api/v1.1/status/create"

            response = requests.post(
                pixelfed_api_status,
                headers=headers,
                files=files,
                data=data,
                timeout=15
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
    Publishes a scheduled post image to all linked Instagram Business Accounts.
    Includes validation, error parsing, and retry logic.

    Args:
        scheduled_post: ScheduledPost instance to publish
        retry_count: Current retry attempt (internal use)
        max_retries: Maximum retry attempts for transient errors
    """
    # Generate a signed URL for Instagram to download the image
    # Use 24-hour expiration to ensure Instagram has plenty of time to download
    image_url = get_s3_signed_url(scheduled_post.image.name, expiration=86400)  # 24-hour expiration
    if not image_url:
        logger.error(f"Could not generate signed URL for scheduled post ID {scheduled_post.id}")
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

    # Validate image URL is accessible
    if not _validate_image_url(image_url):
        logger.error(f"Image URL validation failed for post ID {scheduled_post.id}")
        scheduled_post.status = "failed"
        scheduled_post.save(update_fields=["status"])
        return

    for account in scheduled_post.instagram_accounts.all():
        try:
            # Check if token is expired before attempting post
            if account.expires_at and account.expires_at <= now():
                logger.error(f"Instagram token expired for @{account.username}. Cannot post.")
                continue

            logger.info(f"Posting to Instagram Business Account @{account.username}")

            # Step 1: Create media container
            create_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}/media"
            media_payload = {
                "image_url": image_url,
                "caption": full_caption,
                "access_token": account.access_token,
            }

            logger.debug(f"Creating media container at {create_url}")
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
