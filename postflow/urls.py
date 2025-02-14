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
    path('hashtags/', views.hashtags_view, name='hashtags'),
    path('hashtag-groups/', views.hashtag_groups_view, name='hashtag-groups'),
    path('add-hashtag/', views.add_hashtag_view, name='add-hashtag'),
    path('calendar/', views.calendar_view, name='calendar'),
]
