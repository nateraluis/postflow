from django.contrib import admin

from .models import BlogPost, BlogPostImage, ContentSource, Website


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ("url", "user", "detected_platform", "sync_status", "last_synced_at")
    list_filter = ("sync_status", "detected_platform")


@admin.register(ContentSource)
class ContentSourceAdmin(admin.ModelAdmin):
    list_display = ("website", "kind", "priority", "is_active")
    list_filter = ("kind", "is_active")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "website", "published_at", "promo_count", "last_promoted_at")
    search_fields = ("title", "url")
    date_hierarchy = "published_at"


@admin.register(BlogPostImage)
class BlogPostImageAdmin(admin.ModelAdmin):
    list_display = ("blog_post", "source_url", "is_feature", "order")
