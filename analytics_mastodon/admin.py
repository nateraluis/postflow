"""
Admin interface for Mastodon Analytics models.
"""
from django.contrib import admin
from .models import (
    MastodonPost,
    MastodonFavourite,
    MastodonReply,
    MastodonReblog,
    MastodonEngagementSummary,
)


@admin.register(MastodonPost)
class MastodonPostAdmin(admin.ModelAdmin):
    """Admin interface for Mastodon Posts"""

    list_display = [
        'mastodon_post_id',
        'username',
        'instance_url',
        'media_type',
        'posted_at',
        'get_favourites_count',
        'get_replies_count',
        'get_reblogs_count',
        'last_fetched_at',
    ]

    list_filter = [
        'media_type',
        'instance_url',
        'posted_at',
        'last_fetched_at',
        'visibility',
    ]

    search_fields = [
        'mastodon_post_id',
        'username',
        'content',
    ]

    readonly_fields = [
        'created_at',
        'last_fetched_at',
        'posted_at',
    ]

    date_hierarchy = 'posted_at'

    def get_favourites_count(self, obj):
        """Display favourites count"""
        return obj.favourites.count()
    get_favourites_count.short_description = 'Favourites'

    def get_replies_count(self, obj):
        """Display replies count"""
        return obj.replies.count()
    get_replies_count.short_description = 'Replies'

    def get_reblogs_count(self, obj):
        """Display reblogs count"""
        return obj.reblogs.count()
    get_reblogs_count.short_description = 'Reblogs'


@admin.register(MastodonFavourite)
class MastodonFavouriteAdmin(admin.ModelAdmin):
    """Admin interface for Mastodon Favourites"""

    list_display = [
        'username',
        'post',
        'favourited_at',
    ]

    list_filter = [
        'favourited_at',
    ]

    search_fields = [
        'username',
        'display_name',
        'post__mastodon_post_id',
    ]

    readonly_fields = ['created_at']
    date_hierarchy = 'favourited_at'


@admin.register(MastodonReply)
class MastodonReplyAdmin(admin.ModelAdmin):
    """Admin interface for Mastodon Replies"""

    list_display = [
        'username',
        'post',
        'get_content_preview',
        'is_nested_reply',
        'replied_at',
    ]

    list_filter = [
        'replied_at',
    ]

    search_fields = [
        'username',
        'display_name',
        'content',
        'post__mastodon_post_id',
    ]

    readonly_fields = ['created_at']
    date_hierarchy = 'replied_at'

    def get_content_preview(self, obj):
        """Display truncated reply content"""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    get_content_preview.short_description = 'Content'


@admin.register(MastodonReblog)
class MastodonReblogAdmin(admin.ModelAdmin):
    """Admin interface for Mastodon Reblogs"""

    list_display = [
        'username',
        'post',
        'reblogged_at',
    ]

    list_filter = [
        'reblogged_at',
    ]

    search_fields = [
        'username',
        'display_name',
        'post__mastodon_post_id',
    ]

    readonly_fields = ['created_at']
    date_hierarchy = 'reblogged_at'


@admin.register(MastodonEngagementSummary)
class MastodonEngagementSummaryAdmin(admin.ModelAdmin):
    """Admin interface for Mastodon Engagement Summaries"""

    list_display = [
        'post',
        'total_favourites',
        'total_replies',
        'total_reblogs',
        'total_engagement',
        'last_updated',
    ]

    list_filter = [
        'last_updated',
    ]

    search_fields = [
        'post__mastodon_post_id',
        'post__username',
    ]

    readonly_fields = [
        'total_engagement',
        'last_updated',
    ]

    date_hierarchy = 'last_updated'
