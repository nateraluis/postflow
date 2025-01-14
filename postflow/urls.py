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
]
