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

    @property
    def is_subscribed(self):
        """Check if user has an active subscription"""
        # In DEBUG mode (development), all users are considered subscribed
        if settings.DEBUG:
            return True

        try:
            return self.subscription.is_active
        except AttributeError:
            return False

    @property
    def subscription_status(self):
        """Get user's subscription status"""
        try:
            return self.subscription.status
        except AttributeError:
            return 'none'


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


class ScheduledPost(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("scheduled", "Scheduled"),
        ("posted", "Posted"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="scheduled_posts/", blank=True, null=True)  # Kept for backward compatibility
    caption = models.TextField(blank=True, null=True)
    post_date = models.DateTimeField()
    user_timezone = models.CharField(max_length=50, default="UTC")
    hashtag_groups = models.ManyToManyField("TagGroup", blank=True)
    mastodon_accounts = models.ManyToManyField("pixelfed.MastodonAccount", blank=True, help_text="Pixelfed/Mastodon-compatible instances")
    mastodon_native_accounts = models.ManyToManyField("mastodon_native.MastodonAccount", blank=True, help_text="Native Mastodon instances")
    instagram_accounts = models.ManyToManyField("instagram.InstagramBusinessAccount", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    mastodon_media_id = models.CharField(max_length=255, blank=True, null=True)  # Stores media ID from Mastodon
    mastodon_post_id = models.CharField(max_length=255, blank=True, null=True)  # Stores the scheduled post ID
    instagram_media_id = models.CharField(max_length=255, blank=True, null=True)  # Stores media ID from Instagram
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
        Legacy method for backward compatibility with single image posts.
        """
        if settings.DEBUG:
            return self.image.file if self.image else None

        if not self.image:
            return None

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

    def get_all_images(self):
        """
        Returns a list of all images for this post.
        Checks both the new PostImage model and legacy single image field.
        Returns list of image file objects.
        """
        images = []

        # Get images from PostImage model (new multi-image posts)
        if self.images.exists():
            for post_image in self.images.all():
                img_file = post_image.get_image_file()
                if img_file:
                    images.append(img_file)
        # Fallback to legacy single image field
        elif self.image:
            img_file = self.get_image_file()
            if img_file:
                images.append(img_file)

        return images


class PostImage(models.Model):
    """
    Model for storing multiple images per scheduled post.
    Allows posts to have image carousels/galleries.
    """
    scheduled_post = models.ForeignKey(
        ScheduledPost,
        on_delete=models.CASCADE,
        related_name="images",
        help_text="The scheduled post this image belongs to"
    )
    image = models.ImageField(
        upload_to="scheduled_posts/",
        help_text="Image file for this post"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order of this image in the post (0-indexed)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        verbose_name = "Post Image"
        verbose_name_plural = "Post Images"

    def __str__(self):
        return f"Image {self.order + 1} for {self.scheduled_post}"

    def get_image_file(self):
        """
        Downloads the image file from S3 and returns it as a file-like object (BytesIO).
        Works for both DEBUG and production (S3) modes.
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


class Subscriber(models.Model):
    email = models.EmailField(unique=True, help_text="Email address of the subscriber")
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

    class Meta:
        verbose_name_plural = "Subscribers"
        ordering = ["-subscribed_at"]
