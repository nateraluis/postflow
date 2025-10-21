from django.conf import settings
import boto3
import requests


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
    image_file = scheduled_post.get_image_file()
    if not image_file:
        print(f"❌ Could not get image for scheduled post ID {scheduled_post.id}")
        return
    for account in scheduled_post.mastodon_accounts.all():
        headers = {
            "Authorization": f"Bearer {account.access_token}",
            "Accept": "application/json",
        }
        hashtags = " ".join(
            tag.name
            for tag_group in scheduled_post.hashtag_groups.all()
            for tag in tag_group.tags.all()
        )
        data = {
            "status": scheduled_post.caption + "\n" + hashtags,
            "visibility": "public",
        }
        files = {"file": ("image.jpg", image_file, "image/jpeg")}

        try:
            print(f"Posting to Pixelfed account @{account.username} on {account.instance_url}")
            pixelfed_api_status = account.instance_url + "/api/v1.1/status/create"
            response = requests.post(pixelfed_api_status, headers=headers, files=files, data=data)
            response.raise_for_status()
            post_response = response.json()

            # Update ScheduledPost with Mastodon post ID and status
            scheduled_post.mastodon_post_id = post_response.get("id")
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["mastodon_post_id", "status"])
            print(f"✅ Posted to Pixelfed @{account.username}, post ID: {scheduled_post.mastodon_post_id}")

        except requests.RequestException as e:
            print(f"Failed to schedule post on Mastodon: {e}")


def post_instagram(scheduled_post):
    """
    Publishes a scheduled post image to all linked Instagram Business Accounts.
    """
    # Generate a public (signed) URL for Instagram to curl the image
    image_url = get_s3_signed_url(scheduled_post.image.name)
    if not image_url:
        print(f"❌ Could not generate signed URL for scheduled post ID {scheduled_post.id}")
        scheduled_post.status = "failed"
        scheduled_post.save(update_fields=["status"])
        return

    caption = scheduled_post.caption or ""
    hashtags = " ".join(
        tag.name
        for tag_group in scheduled_post.hashtag_groups.all()
        for tag in tag_group.tags.all()
    )
    full_caption = f"{caption}\n{hashtags}".strip()

    for account in scheduled_post.instagram_accounts.all():
        try:
            print(f"Posting to Instagram Business Account @{account.username}")
            # Step 1: Create media container
            create_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}/media"
            media_payload = {
                "image_url": image_url,
                "caption": full_caption,
                "access_token": account.access_token,
            }

            media_response = requests.post(create_url, data=media_payload)
            media_response.raise_for_status()
            container_id = media_response.json().get("id")

            if media_response.status_code != 200:
                raise Exception(f"Instagram media container creation failed: {media_response.text}")

            if not container_id:
                raise Exception("No container ID returned.")

            # Step 2: Publish the container
            publish_url = f"https://graph.instagram.com/v22.0/{account.instagram_id}/media_publish"
            publish_payload = {
                "creation_id": container_id,
                "access_token": account.access_token,
            }

            publish_response = requests.post(publish_url, data=publish_payload)
            publish_response.raise_for_status()

            ig_media_id = publish_response.json().get("id")
            print(f"✅ Posted to Instagram @{account.username}, media ID: {ig_media_id}")

            # Mark as posted
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["status"])

        except requests.RequestException as e:
            print(f"❌ Instagram post failed for @{account.username}: {e}")
            # print more details. Not only bad request, but the full response
            print(f"Response: {e.response.text if e.response else 'No response'}")
            scheduled_post.status = "failed"
            scheduled_post.save(update_fields=["status"])
