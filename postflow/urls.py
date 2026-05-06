from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile_view, name="profile"),
    path('accounts/', views.accounts_view, name='accounts'),
    path('hashtag-groups/', views.hashtag_groups_view, name='hashtag-groups'),
    path("hashtags/list/", views.hashtag_groups_list_view, name="hashtag-groups-list"),
    path('calendar/', views.calendar_view, name='calendar'),
    path('posted-history/', views.posted_history_view, name='posted_history'),
    path('schedule-post/', views.schedule_post, name="schedule_post"),
    path('drafts/', views.drafts_view, name='drafts'),
    path('post/<int:post_id>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    path('location-search/', views.location_search, name='location_search'),
    path('check-banned-hashtags/', views.check_banned_hashtags_view, name='check_banned_hashtags'),
    path('feedback/', views.feedback_view, name='feedback'),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("subscribe/", views.subscribe, name="subscribe"),

    # Analytics Preview Routes
    path('analytics-preview/', views.analytics_preview_landing, name='analytics_preview_landing'),
    path('analytics-preview/connect/', views.analytics_preview_connect, name='analytics_preview_connect'),
    path('analytics-preview/callback/', views.analytics_preview_callback, name='analytics_preview_callback'),
    path('analytics-preview/dashboard/', views.analytics_preview_dashboard, name='analytics_preview_dashboard'),
]
