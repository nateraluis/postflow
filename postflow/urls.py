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
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("subscribe/", views.subscribe, name="subscribe"),
]
