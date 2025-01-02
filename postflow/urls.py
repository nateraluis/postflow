from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup, name="signup"),
    path("register/", views.register, name="register"),
    path("profile/<str:username>/", views.profile_view, name="profile"),
]
