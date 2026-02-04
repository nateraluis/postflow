from django.db import models
from django.conf import settings
from django.utils.timezone import now, timedelta


class InstagramBusinessAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="instagram_business_accounts")
    instagram_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    access_token = models.TextField(help_text="Page access token with access to IG account")
    expires_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)

    # Sync tracking timestamps
    last_posts_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When posts were last synced from this account"
    )
    last_insights_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When insights data was last fetched for this account"
    )
    next_posts_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the next automatic posts sync is scheduled"
    )
    next_insights_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the next automatic insights sync is scheduled"
    )

    def __str__(self):
        return f"{self.username} (Business)"

    def is_token_expiring(self, days=7):
            return self.expires_at and self.expires_at <= now() + timedelta(days=days)
