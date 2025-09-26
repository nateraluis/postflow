from django.contrib import admin
from .models import StripeCustomer, UserSubscription


@admin.register(StripeCustomer)
class StripeCustomerAdmin(admin.ModelAdmin):
    list_display = ['user', 'stripe_customer_id', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email', 'stripe_customer_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'status', 'current_period_end', 'is_active']
    list_filter = ['status', 'current_period_start', 'current_period_end']
    search_fields = ['user__email', 'stripe_subscription_id']
    readonly_fields = ['created_at', 'updated_at', 'stripe_subscription_id']

    def is_active(self, obj):
        return obj.is_active
    is_active.boolean = True
