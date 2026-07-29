from django.conf import settings
from django.db import models
from django.utils import timezone


class LinkedInAccount(models.Model):
    """A connected LinkedIn member profile (Share on LinkedIn / w_member_social)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="linkedin_accounts"
    )
    member_urn = models.CharField(
        max_length=100, help_text="LinkedIn member URN, e.g. urn:li:person:xxxx"
    )
    username = models.CharField(max_length=150, blank=True, help_text="Display name")
    access_token = models.TextField()
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="LinkedIn tokens last ~60 days and cannot be auto-refreshed; re-auth needed",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username or self.member_urn} (LinkedIn)"

    def is_token_expiring(self, days=7):
        if self.expires_at is None:
            return False
        return self.expires_at <= timezone.now() + timezone.timedelta(days=days)

    @property
    def token_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()
