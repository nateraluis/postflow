from django.conf import settings
from django.db import models


class VoiceProfile(models.Model):
    """Editable writing rules used when the AI drafts social posts for a user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="voice_profiles"
    )
    website = models.ForeignKey(
        "websites.Website", on_delete=models.CASCADE, null=True, blank=True,
        related_name="voice_profiles",
        help_text="Optional: scope this profile to one website",
    )
    name = models.CharField(max_length=100, default="Default")
    is_default = models.BooleanField(default=False)
    rules = models.TextField(
        help_text="Markdown instructions describing the writing voice and platform rules"
    )
    platform_notes = models.JSONField(
        default=dict, blank=True, help_text="Optional per-platform overrides, keyed by platform"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.user})"


class Campaign(models.Model):
    """A promotion effort: one blog post pushed to social platforms over time."""

    GOAL_CHOICES = [
        ("new_issue", "Promote new post"),
        ("evergreen", "Evergreen re-promotion"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("done", "Done"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campaigns"
    )
    website = models.ForeignKey(
        "websites.Website", on_delete=models.CASCADE, related_name="campaigns"
    )
    blog_post = models.ForeignKey(
        "websites.BlogPost", on_delete=models.CASCADE, null=True, blank=True,
        related_name="campaigns",
    )
    name = models.CharField(max_length=255)
    goal = models.CharField(max_length=20, choices=GOAL_CHOICES, default="new_issue")
    utm_campaign = models.SlugField(
        max_length=100, help_text="utm_campaign value used on all links in this campaign"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GeneratedDraft(models.Model):
    """Provenance for an AI-generated ScheduledPost draft."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="drafts")
    scheduled_post = models.OneToOneField(
        "postflow.ScheduledPost", on_delete=models.CASCADE, related_name="generated_draft"
    )
    platform = models.CharField(max_length=30)
    model_used = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=50, default="v1")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.platform} draft for {self.campaign}"


class CampaignReport(models.Model):
    """Weekly AI evaluation of campaign performance (Phase 5)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campaign_reports"
    )
    website = models.ForeignKey(
        "websites.Website", on_delete=models.CASCADE, related_name="campaign_reports",
        null=True, blank=True,
    )
    week_start = models.DateField()
    report_markdown = models.TextField()
    recommendations = models.JSONField(default=list, blank=True)
    model_used = models.CharField(max_length=100, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "website", "week_start"], name="unique_report_per_week"
            )
        ]
        ordering = ["-week_start"]

    def __str__(self):
        return f"Campaign report {self.week_start}"
