from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.signup, name="signup"),
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
]
