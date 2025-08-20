from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.timezone import is_naive
from django.conf import settings
from django.utils.timezone import now, timedelta
from .utils import _get_s3_client
import pytz
from io import BytesIO


class CustomUser(AbstractUser):
    username = None  # Remove the username field
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Tag(models.Model):
    name = models.CharField(max_length=255, db_index=True, help_text="Name of the hashtag (e.g., #example)")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags", help_text="User who owns this tag", default=1)
    
    class Meta:
         constraints = [
            models.UniqueConstraint(fields=["name", "user"], name="unique_tag_per_user")
        ]

    def __str__(self):
        return self.name or "Unnamed Tag"



class TagGroup(models.Model):
    name = models.CharField(max_length=255, db_index=True, help_text="Name of the tag group")
    tags = models.ManyToManyField(Tag, related_name="tag_groups", blank=True, help_text="Tags associated with this group")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tag_groups", help_text="User who owns this tag group")

    class Meta:
         constraints = [
            models.UniqueConstraint(fields=["name", "user"], name="unique_group_per_user")
        ]

    def __str__(self):
        return self.name or "Unnamed Tag Group"


class MastodonAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mastodon_accounts")
    instance_url = models.URLField(help_text="Mastodon or Pixelfed instance URL")
    access_token = models.TextField(help_text="OAuth access token")
    username = models.CharField(max_length=100, help_text="Mastodon username")

    def __str__(self):
        return f"{self.username} @ {self.instance_url}"


class ScheduledPost(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("scheduled", "Scheduled"),
        ("posted", "Posted"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="scheduled_posts/", blank=False, null=False)
    caption = models.TextField(blank=True, null=True)
    post_date = models.DateTimeField()
    user_timezone = models.CharField(max_length=50, default="UTC")
    hashtag_groups = models.ManyToManyField("TagGroup", blank=True)
    mastodon_accounts = models.ManyToManyField("MastodonAccount", blank=True)
    instagram_accounts = models.ManyToManyField("InstagramBusinessAccount", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    mastodon_media_id = models.CharField(max_length=255, blank=True, null=True)  # Stores media ID from Mastodon
    mastodon_post_id = models.CharField(max_length=255, blank=True, null=True)  # Stores the scheduled post ID
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Scheduled Post by {self.user.username} for {self.post_date}"

    def get_local_post_time(self):
        user_tz = pytz.timezone(self.user_timezone)
        return self.post_date.astimezone(user_tz)

    def get_local_post_time_str(self):
        local_dt = self.get_local_post_time()
        return local_dt.strftime("%B %d, %Y, %I:%M %p")  # same as "F j, Y, g:i A"

    def get_image_file(self):
        """
        Downloads the image file from S3 and returns it as a file-like object (BytesIO).
        Works only when DEBUG=False and image is stored in private S3.
        """
        if settings.DEBUG:
            return self.image.file

        s3_client = _get_s3_client()
        bucket_name = settings.AWS_STORAGE_MEDIA_BUCKET_NAME
        object_key = self.image.name  # This is the path/key in S3

        try:
            file_stream = BytesIO()
            s3_client.download_fileobj(bucket_name, object_key, file_stream)
            file_stream.seek(0)
            return file_stream
        except Exception as e:
            print(f"❌ Error downloading image from S3: {e}")
            return None


class InstagramBusinessAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="instagram_business_accounts")
    instagram_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    access_token = models.TextField(help_text="Page access token with access to IG account")
    expires_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.username} (Business)"

    def is_token_expiring(self, days=7):
            return self.expires_at and self.expires_at <= now() + timedelta(days=days)

class Subscriber(models.Model):
    email = models.EmailField(unique=True, help_text="Email address of the subscriber")
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

    class Meta:
        verbose_name_plural = "Subscribers"
        ordering = ["-subscribed_at"]
