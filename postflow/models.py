from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils.timezone import localtime
import pytz


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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="scheduled_posts/", blank=False, null=False)
    caption = models.TextField(blank=True, null=True)
    post_date = models.DateTimeField()
    user_timezone = models.CharField(max_length=50, default="UTC")
    hashtag_groups = models.ManyToManyField("TagGroup", blank=True)
    mastodon_accounts = models.ManyToManyField("MastodonAccount", blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("posted", "Posted"), ("failed", "Failed")],
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Scheduled Post by {self.user.username} for {self.post_date}"

    def get_local_post_time(self):
        user_tz = pytz.timezone(self.user_timezone)
        return localtime(self.post_date, timezone=user_tz)
