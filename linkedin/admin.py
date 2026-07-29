from django.contrib import admin

from .models import LinkedInAccount


@admin.register(LinkedInAccount)
class LinkedInAccountAdmin(admin.ModelAdmin):
    list_display = ("username", "user", "member_urn", "expires_at", "created_at")
