from django.urls import path

from . import views

app_name = "linkedin"

urlpatterns = [
    path("", views.accounts, name="accounts"),
    path("connect/", views.connect_linkedin, name="connect"),
    path("callback/", views.linkedin_callback, name="callback"),
    path("disconnect/<int:pk>/", views.disconnect_linkedin, name="disconnect"),
]
