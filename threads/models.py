from django.conf import settings
from core.fields import EncryptedTextField
from django.db import models
from django.utils import timezone


class ThreadsAccount(models.Model):
    """A connected Threads profile (Meta Threads API)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="threads_accounts"
    )
    threads_user_id = models.CharField(max_length=100)
    username = models.CharField(max_length=150, blank=True)
    access_token = EncryptedTextField(help_text="Long-lived Threads token (refreshable)")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"@{self.username or self.threads_user_id} (Threads)"

    def is_token_expiring(self, days=7):
        if self.expires_at is None:
            return False
        return self.expires_at <= timezone.now() + timezone.timedelta(days=days)
