from django.contrib import admin

from .models import Campaign, CampaignReport, GeneratedDraft, VoiceProfile


@admin.register(VoiceProfile)
class VoiceProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "website", "is_default", "updated_at")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "website", "goal", "status", "utm_campaign", "created_at")
    list_filter = ("goal", "status")


@admin.register(GeneratedDraft)
class GeneratedDraftAdmin(admin.ModelAdmin):
    list_display = ("campaign", "platform", "model_used", "created_at")
    list_filter = ("platform",)


@admin.register(CampaignReport)
class CampaignReportAdmin(admin.ModelAdmin):
    list_display = ("user", "website", "week_start", "model_used", "created_at")
