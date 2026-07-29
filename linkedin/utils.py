import logging

import requests

logger = logging.getLogger("postflow")

LINKEDIN_API_VERSION = "202506"
LINKEDIN_IMAGES_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
MAX_IMAGES = 9

# Reserved characters in LinkedIn's "little text format" for the commentary
# field of the Posts API. Each must be escaped with a preceding backslash.
_RESERVED_CHARS = "\\|{}@[]()<>#*_~"


def _escape_commentary(text: str) -> str:
    """Escape LinkedIn Posts API reserved characters in commentary text."""
    if not text:
        return text
    return "".join(f"\\{ch}" if ch in _RESERVED_CHARS else ch for ch in text)


def _initialize_upload(account, headers):
    """Requests an upload URL + image URN for a single image from LinkedIn."""
    response = requests.post(
        LINKEDIN_IMAGES_URL,
        headers=headers,
        json={"initializeUploadRequest": {"owner": account.member_urn}},
        timeout=15,
    )
    response.raise_for_status()
    value = response.json()["value"]
    return value["uploadUrl"], value["image"]


def post_linkedin(scheduled_post, payload=None):
    """
    Publishes a scheduled post to all linked LinkedIn accounts using the
    LinkedIn Posts API (rest/posts), with support for a single image or a
    multi-image gallery (up to 9 images). Text-only posts are also supported.
    Accepts an optional PostPayload for centralized caption/hashtag assembly.
    Never raises: all failures are logged and result in status="failed".
    """
    if payload is None:
        from postflow.payload import build_payload

        payload = build_payload(scheduled_post)

    caption = payload.get_full_caption("linkedin")

    accounts = list(scheduled_post.linkedin_accounts.all())
    if not accounts:
        logger.error(f"No LinkedIn accounts attached to scheduled post ID {scheduled_post.id}")
        return

    image_files = scheduled_post.get_all_images()[:MAX_IMAGES]

    for account in accounts:
        if account.token_expired:
            logger.error(f"LinkedIn token expired for @{account.username or account.member_urn}. Cannot post.")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
            continue

        headers = {
            "Authorization": f"Bearer {account.access_token}",
            "LinkedIn-Version": LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

        try:
            image_urns = []
            for idx, image_file in enumerate(image_files):
                image_file.seek(0)
                upload_url, image_urn = _initialize_upload(account, headers)

                put_response = requests.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {account.access_token}"},
                    data=image_file.read(),
                    timeout=30,
                )
                put_response.raise_for_status()

                image_urns.append(image_urn)
                logger.debug(
                    f"Uploaded image {idx + 1}/{len(image_files)} to LinkedIn for "
                    f"@{account.username or account.member_urn} - URN: {image_urn}"
                )

            post_body = {
                "author": account.member_urn,
                "commentary": _escape_commentary(caption),
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }

            if len(image_urns) == 1:
                post_body["content"] = {
                    "media": {
                        "id": image_urns[0],
                        "altText": (payload.get_alt_text(0) or "")[:300],
                    }
                }
            elif len(image_urns) > 1:
                post_body["content"] = {
                    "multiImage": {
                        "images": [
                            {"id": urn, "altText": (payload.get_alt_text(idx) or "")[:300]}
                            for idx, urn in enumerate(image_urns)
                        ]
                    }
                }

            logger.debug(f"Creating LinkedIn post with {len(image_urns)} image(s) for @{account.username or account.member_urn}")
            response = requests.post(
                LINKEDIN_POSTS_URL,
                headers=headers,
                json=post_body,
                timeout=15,
            )

            if response.status_code == 201:
                post_urn = response.headers.get("x-restli-id")
                scheduled_post.linkedin_post_id = post_urn
                scheduled_post.status = "posted"
                scheduled_post.save(update_fields=["linkedin_post_id", "status"])
                logger.info(f"Successfully posted to LinkedIn @{account.username or account.member_urn}, post URN: {post_urn}")
            else:
                logger.error(
                    f"Failed to post to LinkedIn @{account.username or account.member_urn}: "
                    f"{response.status_code} {response.text[:500]}"
                )
                scheduled_post.status = "failed"
                scheduled_post.save(update_fields=["status"])

        except requests.exceptions.Timeout:
            logger.error(f"Timeout posting to LinkedIn @{account.username or account.member_urn}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:500] if e.response is not None else "No response"
            logger.error(f"HTTP error posting to LinkedIn @{account.username or account.member_urn}: {status_code}")
            logger.error(f"Response: {body}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
        except requests.RequestException as e:
            logger.error(f"Request failed posting to LinkedIn @{account.username or account.member_urn}: {str(e)}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
        except Exception:
            logger.exception(f"Unexpected error posting to LinkedIn @{account.username or account.member_urn}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
