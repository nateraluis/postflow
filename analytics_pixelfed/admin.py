"""
Admin interface for Pixelfed Analytics models.
"""
from django.contrib import admin
from .models import (
    PixelfedPost,
    PixelfedLike,
    PixelfedComment,
    PixelfedShare,
    PixelfedEngagementSummary,
)


@admin.register(PixelfedPost)
class PixelfedPostAdmin(admin.ModelAdmin):
    """Admin interface for Pixelfed Posts"""

    list_display = [
        'pixelfed_post_id',
        'username',
        'instance_url',
        'media_type',
        'posted_at',
        'get_likes_count',
        'get_comments_count',
        'get_shares_count',
        'last_fetched_at',
    ]

    list_filter = [
        'media_type',
        'instance_url',
        'posted_at',
        'last_fetched_at',
    ]

    search_fields = [
        'pixelfed_post_id',
        'username',
        'caption',
    ]

    readonly_fields = [
        'created_at',
        'last_fetched_at',
        'posted_at',
    ]

    date_hierarchy = 'posted_at'

    def get_likes_count(self, obj):
        """Display likes count"""
        return obj.likes.count()
    get_likes_count.short_description = 'Likes'

    def get_comments_count(self, obj):
        """Display comments count"""
        return obj.comments.count()
    get_comments_count.short_description = 'Comments'

    def get_shares_count(self, obj):
        """Display shares count"""
        return obj.shares.count()
    get_shares_count.short_description = 'Shares'


@admin.register(PixelfedLike)
class PixelfedLikeAdmin(admin.ModelAdmin):
    """Admin interface for Pixelfed Likes"""

    list_display = [
        'username',
        'post',
        'liked_at',
    ]

    list_filter = [
        'liked_at',
    ]

    search_fields = [
        'username',
        'display_name',
        'post__pixelfed_post_id',
    ]

    readonly_fields = ['created_at']
    date_hierarchy = 'liked_at'


@admin.register(PixelfedComment)
class PixelfedCommentAdmin(admin.ModelAdmin):
    """Admin interface for Pixelfed Comments"""

    list_display = [
        'username',
        'post',
        'get_content_preview',
        'is_reply',
        'commented_at',
    ]

    list_filter = [
        'commented_at',
    ]

    search_fields = [
        'username',
        'display_name',
        'content',
        'post__pixelfed_post_id',
    ]

    readonly_fields = ['created_at']
    date_hierarchy = 'commented_at'

    def get_content_preview(self, obj):
        """Display truncated comment content"""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    get_content_preview.short_description = 'Content'


@admin.register(PixelfedShare)
class PixelfedShareAdmin(admin.ModelAdmin):
    """Admin interface for Pixelfed Shares"""

    list_display = [
        'username',
        'post',
        'shared_at',
    ]

    list_filter = [
        'shared_at',
    ]

    search_fields = [
        'username',
        'display_name',
        'post__pixelfed_post_id',
    ]

    readonly_fields = ['created_at']
    date_hierarchy = 'shared_at'


@admin.register(PixelfedEngagementSummary)
class PixelfedEngagementSummaryAdmin(admin.ModelAdmin):
    """Admin interface for Pixelfed Engagement Summaries"""

    list_display = [
        'post',
        'total_likes',
        'total_comments',
        'total_shares',
        'total_engagement',
        'last_updated',
    ]

    list_filter = [
        'last_updated',
    ]

    search_fields = [
        'post__pixelfed_post_id',
        'post__username',
    ]

    readonly_fields = [
        'total_engagement',
        'last_updated',
    ]

    date_hierarchy = 'last_updated'
