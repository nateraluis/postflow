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
    path('feedback/', views.feedback_view, name='feedback'),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("subscribe/", views.subscribe, name="subscribe"),
]
