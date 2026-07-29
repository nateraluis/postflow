from django.urls import path

from . import views

app_name = "threads"

urlpatterns = [
    path("", views.accounts, name="accounts"),
    path("connect/", views.connect_threads, name="connect"),
    path("callback/", views.threads_callback, name="callback"),
    path("disconnect/<int:pk>/", views.disconnect_threads, name="disconnect"),
]
