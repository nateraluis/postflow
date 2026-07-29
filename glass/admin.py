from django.contrib import admin

from .models import GlassAccount, ManualPostTask


@admin.register(GlassAccount)
class GlassAccountAdmin(admin.ModelAdmin):
    list_display = ("username", "user", "created_at")


@admin.register(ManualPostTask)
class ManualPostTaskAdmin(admin.ModelAdmin):
    list_display = ("scheduled_post", "platform", "status", "ready_at", "completed_at")
    list_filter = ("status",)
