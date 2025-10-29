from django.contrib import admin
from .models import MastodonAccount


class MastodonAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'instance_url', 'user')
    search_fields = ('username', 'instance_url', 'user__email')
    list_filter = ('user',)
    ordering = ('username', 'instance_url')


admin.site.register(MastodonAccount, MastodonAccountAdmin)
