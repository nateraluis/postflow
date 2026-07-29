from django.contrib import admin

from .models import AnalyticsConnection, SiteSnapshot


@admin.register(AnalyticsConnection)
class AnalyticsConnectionAdmin(admin.ModelAdmin):
    list_display = ("website", "provider", "is_active", "last_collected_at")
    list_filter = ("provider", "is_active")


@admin.register(SiteSnapshot)
class SiteSnapshotAdmin(admin.ModelAdmin):
    list_display = ("website", "date", "visitors", "pageviews", "subscribers", "subscriber_delta")
    date_hierarchy = "date"
