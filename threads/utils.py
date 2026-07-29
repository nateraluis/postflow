import logging
import time

import requests
from django.utils.timezone import now

logger = logging.getLogger("postflow")

THREADS_GRAPH_BASE = "https://graph.threads.net/v1.0"
THREADS_CAPTION_LIMIT = 500
MAX_PUBLISH_RETRIES = 3
MAX_CREATE_RETRIES = 3


def _validate_threads_caption(caption: str) -> bool:
    """Threads caption limit is ~500 characters."""
    if not caption:
        return True

    if len(caption) > THREADS_CAPTION_LIMIT:
        logger.warning(f"Caption exceeds Threads limit ({THREADS_CAPTION_LIMIT} chars). Length: {len(caption)}")
        return False

    return True


def _validate_image_url(image_url: str, timeout: int = 10) -> bool:
    """
    Validates that an image URL is publicly reachable before handing it to Threads.
    Mirrors instagram/utils.py's _validate_image_url.
    """
    try:
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


def _parse_threads_error(response) -> str:
    """Extracts a readable error message from a Threads Graph API response."""
    try:
        data = response.json()
        error = data.get("error")
        if isinstance(error, dict):
            error_type = error.get("type", "unknown")
            error_code = error.get("code", "unknown")
            error_msg = error.get("message", str(error))
            return f"{error_type} ({error_code}): {error_msg}"
        if error:
            return str(error)
        return response.text[:500]
    except ValueError:
        return response.text[:500]


def _build_public_image_urls(scheduled_post) -> list:
    """
    Builds public, signed image URLs for a scheduled post the same way
    instagram/utils.py does. Threads (unlike Instagram) supports text-only
    posts, so when no publicly reachable URL can be produced -- e.g. in
    DEBUG, where get_s3_signed_url() resolves to a local, non-public
    MEDIA_URL path -- we log a warning and let the caller fall back to a
    text-only post instead of failing outright.
    """
    from postflow.utils import get_s3_signed_url

    raw_urls = []

    if scheduled_post.images.exists():
        for post_image in scheduled_post.images.all():
            image_url = get_s3_signed_url(post_image.image.name, expiration=86400)  # 24-hour expiration
            if image_url:
                raw_urls.append(image_url)
    elif scheduled_post.image:
        image_url = get_s3_signed_url(scheduled_post.image.name, expiration=86400)
        if image_url:
            raw_urls.append(image_url)

    public_urls = [url for url in raw_urls if url.startswith("http://") or url.startswith("https://")]

    if raw_urls and not public_urls:
        logger.warning(
            f"Signed image URL(s) for scheduled post ID {scheduled_post.id} are not publicly reachable "
            "(likely DEBUG mode with no public MEDIA_URL). Falling back to a text-only Threads post."
        )

    return public_urls


def post_threads(scheduled_post, payload=None):
    """
    Publishes a scheduled post to all linked Threads accounts.

    Supports text-only posts (0 images), single-image posts, and carousels
    (2-10 images). Mirrors instagram/utils.py's container -> publish flow,
    retry behaviour, and status handling as closely as Threads' API allows.
    """
    from postflow.payload import build_payload

    if payload is None:
        payload = build_payload(scheduled_post)

    full_caption = payload.get_full_caption("threads")

    if not _validate_threads_caption(full_caption):
        logger.error(f"Invalid caption for scheduled post ID {scheduled_post.id}: exceeds Threads length limit")
        scheduled_post.status = "failed"
        scheduled_post.save(update_fields=["status"])
        return

    image_urls = _build_public_image_urls(scheduled_post)

    # Validate all image URLs are accessible before attempting to post.
    for idx, img_url in enumerate(image_urls):
        if not _validate_image_url(img_url):
            logger.error(f"Image URL validation failed for image {idx + 1} in post ID {scheduled_post.id}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

    is_carousel = len(image_urls) > 1
    if image_urls:
        logger.info(
            f"Posting {'carousel with ' + str(len(image_urls)) + ' images' if is_carousel else 'single image'} "
            "to Threads"
        )
    else:
        logger.info("Posting text-only update to Threads")

    for account in scheduled_post.threads_accounts.all():
        try:
            if account.expires_at and account.expires_at <= now():
                # Skip this account but keep trying the remaining ones
                logger.error(f"Threads token expired for @{account.username}. Cannot post.")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                continue

            logger.info(f"Posting to Threads account @{account.username}")

            create_url = f"{THREADS_GRAPH_BASE}/{account.threads_user_id}/threads"
            container_id = None

            if not image_urls:
                # Text-only post
                media_payload = {
                    "media_type": "TEXT",
                    "text": full_caption,
                    "access_token": account.access_token,
                }
                media_response = _post_with_retry(create_url, media_payload, account, "text container")
                if media_response is None:
                    scheduled_post.status = "failed"
                    scheduled_post.save(update_fields=["status"])
                    return
                container_id = media_response.json().get("id")

            elif not is_carousel:
                # Single image post
                media_payload = {
                    "media_type": "IMAGE",
                    "image_url": image_urls[0],
                    "text": full_caption,
                    "access_token": account.access_token,
                }
                media_response = _post_with_retry(create_url, media_payload, account, "image container")
                if media_response is None:
                    scheduled_post.status = "failed"
                    scheduled_post.save(update_fields=["status"])
                    return
                container_id = media_response.json().get("id")

            else:
                # Carousel: create one child container per image, then a parent carousel container
                child_ids = []
                for idx, img_url in enumerate(image_urls):
                    child_payload = {
                        "media_type": "IMAGE",
                        "image_url": img_url,
                        "is_carousel_item": "true",
                        "access_token": account.access_token,
                    }
                    child_response = _post_with_retry(
                        create_url, child_payload, account, f"carousel child container {idx + 1}"
                    )
                    if child_response is None:
                        scheduled_post.status = "failed"
                        scheduled_post.save(update_fields=["status"])
                        return

                    child_id = child_response.json().get("id")
                    if not child_id:
                        logger.error(f"No container ID returned for carousel child {idx + 1} for @{account.username}")
                        scheduled_post.status = "failed"
                        scheduled_post.save(update_fields=["status"])
                        return
                    child_ids.append(child_id)

                carousel_payload = {
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_ids),
                    "text": full_caption,
                    "access_token": account.access_token,
                }
                media_response = _post_with_retry(create_url, carousel_payload, account, "carousel container")
                if media_response is None:
                    scheduled_post.status = "failed"
                    scheduled_post.save(update_fields=["status"])
                    return
                container_id = media_response.json().get("id")

            if not container_id:
                logger.error(f"No container ID returned by Threads for @{account.username}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            logger.debug(f"Created Threads container: {container_id}")

            # Publish the container, retrying briefly while it finishes processing.
            publish_url = f"{THREADS_GRAPH_BASE}/{account.threads_user_id}/threads_publish"
            publish_payload = {
                "creation_id": container_id,
                "access_token": account.access_token,
            }

            publish_response = None
            for attempt in range(MAX_PUBLISH_RETRIES):
                logger.debug(f"Publishing Threads container (attempt {attempt + 1}/{MAX_PUBLISH_RETRIES})")
                publish_response = requests.post(publish_url, data=publish_payload, timeout=15)

                if publish_response.status_code == 200:
                    break

                error_msg = _parse_threads_error(publish_response)
                retryable = publish_response.status_code >= 500 or "not ready" in error_msg.lower()

                if retryable and attempt < MAX_PUBLISH_RETRIES - 1:
                    wait_time = 2 * (attempt + 1)
                    logger.warning(
                        f"Threads container not ready to publish for @{account.username} ({error_msg}). "
                        f"Retrying in {wait_time}s (attempt {attempt + 1}/{MAX_PUBLISH_RETRIES})"
                    )
                    time.sleep(wait_time)
                    continue

                logger.error(f"Failed to publish Threads post for @{account.username}: {error_msg}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            if publish_response.status_code != 200:
                error_msg = _parse_threads_error(publish_response)
                logger.error(f"Failed to publish Threads post for @{account.username} after retries: {error_msg}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            try:
                publish_data = publish_response.json()
            except ValueError as e:
                logger.error(f"Error parsing Threads publish response for @{account.username}: {e}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            threads_post_id = publish_data.get("id")
            if not threads_post_id:
                logger.error(f"No post ID returned by Threads publish for @{account.username}")
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])
                return

            logger.info(f"Successfully posted to Threads @{account.username}, post ID: {threads_post_id}")
            scheduled_post.threads_post_id = threads_post_id
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["threads_post_id", "status"])

        except requests.exceptions.Timeout:
            logger.error(f"Timeout posting to Threads @{account.username}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error posting to Threads @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

        except requests.RequestException as e:
            logger.error(f"Request exception posting to Threads @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return

        except Exception as e:
            logger.exception(f"Unexpected error posting to Threads @{account.username}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            return


def _post_with_retry(url, data, account, label):
    """
    POSTs a container-creation request, retrying on transient (5xx) failures.
    Returns the successful response, or None if all attempts failed (already logged).
    """
    response = None
    for attempt in range(MAX_CREATE_RETRIES):
        response = requests.post(url, data=data, timeout=15)

        if response.status_code == 200:
            return response

        error_msg = _parse_threads_error(response)
        if response.status_code >= 500 and attempt < MAX_CREATE_RETRIES - 1:
            wait_time = 3 * (attempt + 1)
            logger.warning(
                f"Transient error creating {label} for @{account.username}: {error_msg}. "
                f"Retrying in {wait_time}s (attempt {attempt + 1}/{MAX_CREATE_RETRIES})"
            )
            time.sleep(wait_time)
            continue

        logger.error(f"Failed to create {label} for @{account.username}: {error_msg}")
        return None

    return None
