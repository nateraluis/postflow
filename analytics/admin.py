"""
Admin configuration for analytics app.
"""
from django.contrib import admin
from .models import PostAnalytics


@admin.register(PostAnalytics)
class PostAnalyticsAdmin(admin.ModelAdmin):
    """Admin interface for Post Analytics."""

    list_display = [
        'scheduled_post',
        'platform',
        'likes',
        'comments',
        'shares',
        'total_engagement',
        'engagement_rate',
        'last_updated',
    ]

    list_filter = [
        'platform',
        'last_updated',
        'created_at',
    ]

    search_fields = [
        'scheduled_post__caption',
        'platform_post_id',
    ]

    readonly_fields = [
        'created_at',
        'last_updated',
        'total_engagement',
    ]

    fieldsets = (
        ('Post Information', {
            'fields': ('scheduled_post', 'platform', 'platform_post_id')
        }),
        ('Engagement Metrics', {
            'fields': ('likes', 'comments', 'shares', 'saved', 'impressions', 'reach', 'engagement_rate')
        }),
        ('Tracking', {
            'fields': ('created_at', 'last_updated')
        }),
    )

    def total_engagement(self, obj):
        """Display total engagement in admin list."""
        return obj.total_engagement
    total_engagement.short_description = 'Total Engagement'

    ordering = ['-last_updated']
