from django.db import models


class AnalyticsConnection(models.Model):
    """A per-website analytics data source the user has connected."""

    PROVIDER_CHOICES = [
        ("plausible", "Plausible Analytics"),
        ("gsc", "Google Search Console"),
        ("ghost_admin", "Ghost members / email stats"),
    ]

    website = models.ForeignKey(
        "websites.Website", on_delete=models.CASCADE, related_name="analytics_connections"
    )
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    config = models.JSONField(
        default=dict, blank=True,
        help_text="Provider credentials/config, e.g. {'api_key': ..., 'site_id': ...}",
    )
    is_active = models.BooleanField(default=True)
    last_collected_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["website", "provider"], name="unique_provider_per_website"
            )
        ]

    def __str__(self):
        return f"{self.website}: {self.get_provider_display()}"


class SiteSnapshot(models.Model):
    """One day of website analytics: raw provider payloads plus denormalised KPIs."""

    website = models.ForeignKey(
        "websites.Website", on_delete=models.CASCADE, related_name="site_snapshots"
    )
    date = models.DateField(db_index=True)
    days = models.IntegerField(default=1, help_text="Collection window in days")

    ghost = models.JSONField(default=dict, blank=True)
    plausible = models.JSONField(default=dict, blank=True)
    gsc = models.JSONField(default=dict, blank=True)
    suggest = models.JSONField(default=dict, blank=True)

    visitors = models.IntegerField(null=True, blank=True)
    pageviews = models.IntegerField(null=True, blank=True)
    subscribers = models.IntegerField(
        null=True, blank=True, help_text="Total newsletter members on this date"
    )
    subscriber_delta = models.IntegerField(null=True, blank=True)

    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["website", "date"], name="unique_site_snapshot_per_day")
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.website} snapshot {self.date}"
