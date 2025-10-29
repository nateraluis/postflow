from django.urls import path
from . import views

app_name = 'pixelfed'

urlpatterns = [
    path("connect/", views.connect_mastodon, name="connect_mastodon"),
    path("callback/", views.mastodon_callback, name="mastodon_callback"),
    path("disconnect/<int:account_id>/", views.disconnect_mastodon, name="disconnect_mastodon"),
]
