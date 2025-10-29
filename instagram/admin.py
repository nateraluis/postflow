from django.contrib import admin
from .models import InstagramBusinessAccount


class InstagramBusinessAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'instagram_id', 'user', 'expires_at', 'last_refreshed_at')
    search_fields = ('username', 'instagram_id', 'user__email')
    list_filter = ('user', 'expires_at')
    ordering = ('-expires_at', 'username')
    readonly_fields = ('instagram_id', 'last_refreshed_at')


admin.site.register(InstagramBusinessAccount, InstagramBusinessAccountAdmin)
