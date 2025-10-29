from django.contrib import admin
from .models import MastodonAccount


@admin.register(MastodonAccount)
class MastodonAccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'instance_url', 'user')
    search_fields = ('username', 'instance_url')
    list_filter = ('instance_url',)
    readonly_fields = ('access_token',)
