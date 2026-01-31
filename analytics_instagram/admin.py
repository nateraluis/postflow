from django.contrib import admin
from .models import InstagramPost, InstagramComment, InstagramEngagementSummary


@admin.register(InstagramPost)
class InstagramPostAdmin(admin.ModelAdmin):
    list_display = [
        'instagram_media_id',
        'username',
        'media_type',
        'posted_at',
        'api_like_count',
        'api_reach',
        'api_impressions'
    ]
    list_filter = ['media_type', 'account', 'posted_at']
    search_fields = ['caption', 'username', 'instagram_media_id']
    readonly_fields = ['created_at', 'last_fetched_at']
    date_hierarchy = 'posted_at'

    fieldsets = (
        ('Post Information', {
            'fields': ('instagram_media_id', 'account', 'username', 'scheduled_post')
        }),
        ('Content', {
            'fields': ('caption', 'media_url', 'media_type', 'permalink')
        }),
        ('Basic Metrics', {
            'fields': ('api_like_count', 'api_comments_count')
        }),
        ('Insights Metrics', {
            'fields': ('api_engagement', 'api_saved', 'api_reach', 'api_impressions', 'api_video_views')
        }),
        ('Timestamps', {
            'fields': ('posted_at', 'last_fetched_at', 'created_at')
        }),
    )


@admin.register(InstagramComment)
class InstagramCommentAdmin(admin.ModelAdmin):
    list_display = ['comment_id', 'username', 'post', 'timestamp', 'like_count', 'is_reply']
    list_filter = ['timestamp', 'post__account']
    search_fields = ['text', 'username', 'comment_id']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Comment Information', {
            'fields': ('comment_id', 'post', 'username')
        }),
        ('Content', {
            'fields': ('text', 'like_count')
        }),
        ('Threading', {
            'fields': ('parent_comment_id',)
        }),
        ('Timestamps', {
            'fields': ('timestamp', 'created_at')
        }),
    )


@admin.register(InstagramEngagementSummary)
class InstagramEngagementSummaryAdmin(admin.ModelAdmin):
    list_display = [
        'post',
        'total_engagement',
        'total_likes',
        'total_comments',
        'total_saved',
        'total_reach',
        'engagement_rate'
    ]
    readonly_fields = ['last_updated']
    search_fields = ['post__instagram_media_id', 'post__username']

    fieldsets = (
        ('Post', {
            'fields': ('post',)
        }),
        ('Engagement Metrics', {
            'fields': ('total_likes', 'total_comments', 'total_saved', 'total_engagement')
        }),
        ('Reach Metrics', {
            'fields': ('total_reach', 'total_impressions', 'total_video_views')
        }),
        ('Calculated Metrics', {
            'fields': ('engagement_rate',)
        }),
        ('Timestamps', {
            'fields': ('last_updated',)
        }),
    )
