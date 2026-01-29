"""
Signals for Pixelfed Analytics app.

Automatically creates PixelfedEngagementSummary when a PixelfedPost is created.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PixelfedPost, PixelfedEngagementSummary


@receiver(post_save, sender=PixelfedPost)
def create_engagement_summary(sender, instance, created, **kwargs):
    """
    Automatically create a PixelfedEngagementSummary for new PixelfedPost instances.

    This ensures all posts have an engagement_summary, even if it's all zeros initially.
    This allows sorting by engagement metrics to work correctly.
    """
    if created:
        # Create an empty engagement summary with all zeros
        PixelfedEngagementSummary.objects.get_or_create(post=instance)
