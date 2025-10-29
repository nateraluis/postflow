from django.conf import settings
from django.utils.timezone import now
import boto3
import logging

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
