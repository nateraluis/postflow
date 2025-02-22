import boto3
from django.conf import settings

def get_s3_signed_url(file_path, expiration=3600):
    """
    Generates a secure, temporary signed URL for private S3 media files.
    - file_path: Path to the file in the S3 bucket (e.g., "scheduled_posts/user_1_1714000000.png")
    - expiration: Time (in seconds) before the URL expires (default: 1 hour)
    """
    # if settings.DEBUG:
        # return f"{settings.MEDIA_URL}{file_path}"
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    bucket_name = settings.AWS_STORAGE_MEDIA_BUCKET_NAME

    try:
        signed_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": file_path},
            ExpiresIn=expiration,
        )
        print(signed_url)
        return signed_url
    except Exception as e:
        print(f"Error generating signed URL: {e}")
        return None
