from django.conf import settings
from django.db import models


class GlassAccount(models.Model):
    """A Glass profile. Glass has no public posting API, so posts targeting it
    become manual tasks the user completes from the manual queue."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="glass_accounts"
    )
    username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"@{self.username} (Glass)"


class ManualPostTask(models.Model):
    """A post that must be published by hand on a platform without an API."""

    STATUS_CHOICES = [
        ("waiting", "Waiting for schedule"),
        ("ready", "Ready to post"),
        ("posted", "Posted"),
        ("skipped", "Skipped"),
    ]

    scheduled_post = models.ForeignKey(
        "postflow.ScheduledPost", on_delete=models.CASCADE, related_name="manual_tasks"
    )
    platform = models.CharField(max_length=30, default="glass")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    ready_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    posted_url = models.URLField(blank=True, help_text="Optional link to the published post")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Manual {self.platform} task for post {self.scheduled_post_id} ({self.status})"
