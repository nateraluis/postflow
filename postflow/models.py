from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.timezone import is_naive
from django.conf import settings
from django.utils.timezone import now, timedelta
from .utils import _get_s3_client
import pytz
from io import BytesIO


class CustomUserManager(BaseUserManager):
    """
    Custom user manager for CustomUser model that uses email instead of username.
    """
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular user with the given email and password.
        """
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None  # Remove the username field
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

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
    name = models.CharField(max_length=255, db_index=True, help_text="Hashtag stored without # prefix (e.g., 'example')")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags", help_text="User who owns this tag", default=1)
    pinned = models.BooleanField(default=False, help_text="If true, always included when this tag's group is selected")

    class Meta:
         constraints = [
            models.UniqueConstraint(fields=["name", "user"], name="unique_tag_per_user")
        ]

    def save(self, *args, **kwargs):
        # Normalize: strip # prefix and lowercase
        if self.name:
            self.name = self.name.lstrip("#").strip().lower()
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        """Returns the hashtag with # prefix for display."""
        return f"#{self.name}" if self.name else ""

    @property
    def hashtag(self):
        """Returns the hashtag with # prefix for publishing."""
        return f"#{self.name}" if self.name else ""

    def __str__(self):
        return self.display_name or "Unnamed Tag"



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


class ScheduledThread(models.Model):
    """A thread groups multiple ScheduledPosts into a connected reply chain."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="threads")
    title = models.CharField(max_length=255, blank=True, default="", help_text="Internal label for this thread")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Thread #{self.pk}"

    @property
    def post_count(self):
        return self.posts.count()


class ScheduledPost(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending", "Pending"),
        ("scheduled", "Scheduled"),
        ("posted", "Posted"),
        ("failed", "Failed"),
    ]

    VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("unlisted", "Unlisted"),
        ("private", "Followers only"),
        ("direct", "Direct message"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="scheduled_posts/", blank=True, null=True)  # Kept for backward compatibility
    caption = models.TextField(blank=True, null=True)
    spoiler_text = models.CharField(max_length=500, blank=True, default="", help_text="Content warning text (Mastodon/Pixelfed CW). Ignored on Instagram.")
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="public", help_text="Post visibility on Mastodon/Pixelfed. Instagram is always public.")
    language = models.CharField(max_length=10, blank=True, default="", help_text="ISO 639-1 language code (e.g. en, es, de). Used on Mastodon/Pixelfed.")
    post_date = models.DateTimeField()
    user_timezone = models.CharField(max_length=50, default="UTC")
    hashtag_groups = models.ManyToManyField("TagGroup", blank=True)
    mastodon_accounts = models.ManyToManyField("pixelfed.MastodonAccount", blank=True, help_text="Pixelfed/Mastodon-compatible instances")
    mastodon_native_accounts = models.ManyToManyField("mastodon_native.MastodonAccount", blank=True, help_text="Native Mastodon instances")
    instagram_accounts = models.ManyToManyField("instagram.InstagramBusinessAccount", blank=True)
    location = models.ForeignKey("Location", on_delete=models.SET_NULL, blank=True, null=True, help_text="Location tag for Instagram posts")
    collaborators = models.CharField(max_length=500, blank=True, default="", help_text="Comma-separated Instagram collaborator usernames (max 3)")
    delete_after_hours = models.PositiveIntegerField(blank=True, null=True, help_text="Auto-delete post after N hours (Mastodon/Pixelfed only)")
    thread = models.ForeignKey("ScheduledThread", on_delete=models.CASCADE, blank=True, null=True, related_name="posts", help_text="Thread this post belongs to")
    thread_order = models.PositiveIntegerField(default=0, help_text="Order within thread (0 = first post)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    mastodon_media_id = models.CharField(max_length=255, blank=True, null=True)  # Stores media ID from Mastodon
    mastodon_post_id = models.CharField(max_length=255, blank=True, null=True)  # Stores the scheduled post ID
    instagram_media_id = models.CharField(max_length=255, blank=True, null=True)  # Stores media ID from Instagram
    instagram_post_id = models.CharField(max_length=255, blank=True, null=True)  # Stores the actual Instagram post ID after publishing
    pixelfed_post_id = models.CharField(max_length=255, blank=True, null=True)  # Stores Pixelfed post ID
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
    alt_text = models.TextField(
        blank=True,
        default="",
        help_text="Alt text for accessibility (passed to all platforms)"
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


class Location(models.Model):
    """Saved locations for Instagram location tagging."""
    name = models.CharField(max_length=255)
    facebook_page_id = models.CharField(max_length=255, help_text="Facebook Places page ID for Instagram API")
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="locations")
    use_count = models.PositiveIntegerField(default=0, help_text="Track usage for frequently-used sorting")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facebook_page_id", "user"], name="unique_location_per_user")
        ]
        ordering = ["-use_count", "name"]

    def __str__(self):
        return self.name


class UserTag(models.Model):
    """User/account tags for posts. Positional (x,y) for Instagram, mention-based for Mastodon/Pixelfed."""
    PLATFORM_CHOICES = [
        ("instagram", "Instagram"),
        ("mastodon", "Mastodon"),
        ("pixelfed", "Pixelfed"),
    ]
    scheduled_post = models.ForeignKey(ScheduledPost, on_delete=models.CASCADE, related_name="user_tags")
    post_image = models.ForeignKey(PostImage, on_delete=models.CASCADE, related_name="user_tags", blank=True, null=True)
    username = models.CharField(max_length=255, help_text="Username to tag (e.g., @user or @user@instance)")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="instagram")
    x = models.FloatField(blank=True, null=True, help_text="X position (0-1) for Instagram image tags")
    y = models.FloatField(blank=True, null=True, help_text="Y position (0-1) for Instagram image tags")

    class Meta:
        verbose_name = "User Tag"
        verbose_name_plural = "User Tags"

    def __str__(self):
        return f"@{self.username} on {self.platform}"


class DefaultTag(models.Model):
    """Accounts that a user always wants to tag (auto-filled in composer)."""
    PLATFORM_CHOICES = UserTag.PLATFORM_CHOICES
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="default_tags")
    username = models.CharField(max_length=255)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="instagram")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "username", "platform"], name="unique_default_tag")
        ]

    def __str__(self):
        return f"@{self.username} ({self.platform})"


class HashtagUsage(models.Model):
    """Tracks which hashtags were used on each post for rotation and analytics."""
    scheduled_post = models.ForeignKey(ScheduledPost, on_delete=models.CASCADE, related_name="hashtag_usages")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="usages")
    platform = models.CharField(max_length=20, default="all")
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-used_at"]

    def __str__(self):
        return f"#{self.tag.name} used on post {self.scheduled_post_id}"


class ScheduledBoost(models.Model):
    """Schedule a reblog/boost of someone else's post."""
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("posted", "Posted"),
        ("failed", "Failed"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scheduled_boosts")
    status_url = models.URLField(help_text="URL of the status to boost")
    status_id = models.CharField(max_length=255, blank=True, default="", help_text="Resolved status ID on target instance")
    boost_date = models.DateTimeField()
    mastodon_accounts = models.ManyToManyField("pixelfed.MastodonAccount", blank=True)
    mastodon_native_accounts = models.ManyToManyField("mastodon_native.MastodonAccount", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["boost_date"]

    def __str__(self):
        return f"Boost {self.status_url} at {self.boost_date}"


class FollowerSnapshot(models.Model):
    """Daily snapshot of follower/following/post counts for tracking growth."""
    PLATFORM_CHOICES = [
        ("pixelfed", "Pixelfed"),
        ("mastodon", "Mastodon"),
        ("mastodon_native", "Mastodon (Native)"),
        ("instagram", "Instagram"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follower_snapshots")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_username = models.CharField(max_length=255)
    instance_url = models.URLField(blank=True, default="")
    date = models.DateField(db_index=True)
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)
    posts_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "platform", "account_username", "date"],
                name="unique_snapshot_per_day",
            )
        ]

    def __str__(self):
        return f"@{self.account_username} on {self.date}: {self.followers_count} followers"


class RSSFeed(models.Model):
    """RSS feed to monitor for auto-posting new entries."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rss_feeds")
    name = models.CharField(max_length=255, help_text="Label for this feed")
    url = models.URLField(help_text="RSS/Atom feed URL")
    caption_template = models.TextField(
        default="{title}\n\n{url}",
        help_text="Template for post caption. Variables: {title}, {url}, {summary}, {author}"
    )
    is_active = models.BooleanField(default=True)
    include_instagram = models.BooleanField(default=False, help_text="Also post to Instagram accounts")
    mastodon_accounts = models.ManyToManyField("pixelfed.MastodonAccount", blank=True)
    mastodon_native_accounts = models.ManyToManyField("mastodon_native.MastodonAccount", blank=True)
    instagram_accounts = models.ManyToManyField("instagram.InstagramBusinessAccount", blank=True)
    last_checked_at = models.DateTimeField(blank=True, null=True)
    last_entry_guid = models.CharField(max_length=500, blank=True, default="", help_text="GUID of last processed entry")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class CaptionTemplate(models.Model):
    """Reusable caption structures with placeholders."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="caption_templates")
    name = models.CharField(max_length=100)
    content = models.TextField(help_text="Use {title}, {description}, {date} as placeholders")
    created_at = models.DateTimeField(auto_now_add=True)
    use_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-use_count", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["name", "user"], name="unique_template_per_user")
        ]

    def __str__(self):
        return self.name


class UserDefaults(models.Model):
    """Per-user default settings for the post composer."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posting_defaults")
    default_hashtag_groups = models.ManyToManyField(TagGroup, blank=True, related_name="+")
    default_mastodon_accounts = models.ManyToManyField("pixelfed.MastodonAccount", blank=True, related_name="+")
    default_mastodon_native_accounts = models.ManyToManyField("mastodon_native.MastodonAccount", blank=True, related_name="+")
    default_instagram_accounts = models.ManyToManyField("instagram.InstagramBusinessAccount", blank=True, related_name="+")
    default_location = models.ForeignKey(Location, on_delete=models.SET_NULL, blank=True, null=True, related_name="+")
    default_caption_template = models.ForeignKey(CaptionTemplate, on_delete=models.SET_NULL, blank=True, null=True, related_name="+")

    class Meta:
        verbose_name_plural = "User Defaults"

    def __str__(self):
        return f"Defaults for {self.user.email}"


class Feedback(models.Model):
    CATEGORY_CHOICES = [
        ('improvement', 'Improvement'),
        ('bug', 'Bug Report'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedback_submissions',
        help_text="User who submitted the feedback"
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        help_text="Type of feedback"
    )
    message = models.TextField(
        help_text="Feedback message"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Current status of the feedback"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'

    def __str__(self):
        return f"{self.get_category_display()} from {self.user.email} - {self.created_at.strftime('%Y-%m-%d')}"


class Subscriber(models.Model):
    email = models.EmailField(unique=True, help_text="Email address of the subscriber")
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

    class Meta:
        verbose_name_plural = "Subscribers"
        ordering = ["-subscribed_at"]
