from django.contrib import admin

from .models import ThreadsAccount


@admin.register(ThreadsAccount)
class ThreadsAccountAdmin(admin.ModelAdmin):
    list_display = ("username", "user", "threads_user_id", "expires_at", "created_at")
