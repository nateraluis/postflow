from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    path("profile/<str:username>/", views.profile_view, name="profile"),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('hashtag-groups/', views.hashtag_groups_view, name='hashtag-groups'),
    path("hashtags/list/", views.hashtag_groups_list_view, name="hashtag-groups-list"),
    path('calendar/', views.calendar_view, name='calendar'),
    path('schedule-post/', views.schedule_post, name="schedule_post"),
    path("mastodon/connect/", views.connect_mastodon, name="connect_mastodon"),
    path("mastodon/callback/", views.mastodon_callback, name="mastodon_callback"),
    path("mastodon/disconnect/<int:account_id>/", views.disconnect_mastodon, name="disconnect_mastodon"),
    path("instagram/connect/", views.connect_instagram, name="connect_instagram"),
    path("webhooks/facebook/", views.facebook_webhook, name="facebook_webhook"),
    path("accounts/instagram/business/callback/", views.instagram_business_callback, name="instagram_business_callback"),
    path("accounts/instagram/business/deauthorize/", views.instagram_deauthorize, name="instagram_business_deauthorize"),
    path("accounts/instagram/business/data-deletion/", views.instagram_data_deletion, name="instagram_business_data_deletion"),
    path("instagram/disconnect/<int:account_id>/", views.disconnect_instagram, name="disconnect_instagram"),
]
