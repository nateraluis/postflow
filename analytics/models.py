"""
Analytics models for tracking post engagement metrics.
"""
from django.db import models
from django.conf import settings
from decimal import Decimal


class PostAnalytics(models.Model):
    """
    Store analytics data for published posts.

    Tracks engagement metrics (likes, comments, shares, impressions) from
    Instagram, Mastodon, and Pixelfed posts.
    """

    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('mastodon', 'Mastodon'),
        ('pixelfed', 'Pixelfed'),
    ]

    scheduled_post = models.ForeignKey(
        'postflow.ScheduledPost',
        on_delete=models.CASCADE,
        related_name='analytics',
        help_text="The post this analytics data belongs to"
    )

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        help_text="Platform where the post was published"
    )

    platform_post_id = models.CharField(
        max_length=255,
        help_text="ID of the post on the platform"
    )

    # Engagement Metrics
    likes = models.IntegerField(
        default=0,
        help_text="Number of likes/favorites"
    )

    comments = models.IntegerField(
        default=0,
        help_text="Number of comments/replies"
    )

    shares = models.IntegerField(
        default=0,
        help_text="Number of shares/reblogs (Mastodon/Pixelfed only)"
    )

    impressions = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of times the post was seen (Instagram only)"
    )

    reach = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of unique accounts reached (Instagram only)"
    )

    saved = models.IntegerField(
        default=0,
        help_text="Number of times the post was saved (Instagram only)"
    )

    engagement_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Engagement rate percentage (calculated field)"
    )

    # Tracking
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last time analytics were fetched"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this analytics record was created"
    )

    class Meta:
        verbose_name = "Post Analytics"
        verbose_name_plural = "Post Analytics"
        unique_together = [['scheduled_post', 'platform', 'platform_post_id']]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['scheduled_post', 'platform']),
            models.Index(fields=['last_updated']),
        ]

    def __str__(self):
        return f"{self.platform.title()} analytics for post {self.scheduled_post.id}"

    def calculate_engagement_rate(self, follower_count=None):
        """
        Calculate engagement rate as percentage.

        Formula: (likes + comments + shares) / impressions * 100
        If impressions not available, uses follower_count if provided.
        """
        if not follower_count and not self.impressions:
            return None

        total_engagement = self.likes + self.comments + self.shares
        denominator = self.impressions if self.impressions else follower_count

        if denominator and denominator > 0:
            rate = (total_engagement / denominator) * 100
            return round(Decimal(rate), 2)

        return None

    def save(self, *args, **kwargs):
        """Auto-calculate engagement rate on save if possible."""
        if self.impressions:
            self.engagement_rate = self.calculate_engagement_rate()
        super().save(*args, **kwargs)

    @property
    def total_engagement(self):
        """Total engagement count (likes + comments + shares)."""
        return self.likes + self.comments + self.shares
