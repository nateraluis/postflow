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
        hashtags = ""
        for tag_group in scheduled_post.hashtag_groups.all():
            for tag in tag_group.tags.all():
                hashtags += " " + tag.name
        data = {
            "status": scheduled_post.caption + " " + hashtags,
            "visibility": "public",
        }
        # response = requests.get(image_url, stream=True)  # Ensure it's accessible
        # response.raise_for_status()
        files = {"file": ("image.jpg", image_file, "image/jpeg")}

        try:
            pixelfed_api_status = account.instance_url + "/api/v1.1/status/create"
            response = requests.post(pixelfed_api_status, headers=headers, files=files, data=data)
            response.raise_for_status()
            post_response = response.json()

            # Update ScheduledPost with Mastodon post ID and status
            scheduled_post.mastodon_post_id = post_response.get("id")
            scheduled_post.status = "posted"
            scheduled_post.save(update_fields=["mastodon_post_id", "status"])

        except requests.RequestException as e:
            print(f"Failed to schedule post on Mastodon: {e}")
