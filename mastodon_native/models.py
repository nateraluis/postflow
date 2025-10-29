from django.db import models
from django.conf import settings


class MastodonAccount(models.Model):
    """Mastodon-specific account model for native Mastodon instances"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mastodon_native_accounts")
    instance_url = models.URLField(help_text="Mastodon instance URL")
    access_token = models.TextField(help_text="OAuth access token")
    username = models.CharField(max_length=100, help_text="Mastodon username")

    def __str__(self):
        return f"{self.username} @ {self.instance_url}"
