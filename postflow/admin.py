from django.contrib import admin

from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, Tag, TagGroup


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm

    list_display = ("email", "first_name", "last_name", "is_staff")
    list_filter = ("is_staff", "is_active")
    ordering = ("email",)  # Use email for ordering
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name")}),
        ("Permissions", {"fields": ("is_staff", "is_active", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2", "is_staff", "is_active"),
        }),
    )


class TagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in list view
    search_fields = ('name',)      # Enable search by name
    ordering = ('name',)           # Default ordering by name


class TagGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user')  # Display ID, name, and associated user
    search_fields = ('name', 'user__email')  # Enable search by group name and user email
    list_filter = ('user',)                 # Add filter by user
    ordering = ('name', 'user')             # Default ordering by name and user
    filter_horizontal = ('tags',)           # For better UI when selecting many-to-many tags


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(TagGroup, TagGroupAdmin)

