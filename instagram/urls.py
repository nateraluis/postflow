from django.urls import path
from . import views

app_name = 'instagram'

urlpatterns = [
    path("connect/", views.connect_instagram, name="connect_instagram"),
    path("callback/", views.instagram_business_callback, name="instagram_business_callback"),
    path("disconnect/<int:account_id>/", views.disconnect_instagram, name="disconnect_instagram"),
    path("deauthorize/", views.instagram_deauthorize, name="instagram_business_deauthorize"),
    path("data-deletion/", views.instagram_data_deletion, name="instagram_business_data_deletion"),
    path("webhook/", views.facebook_webhook, name="facebook_webhook"),
]
