from django.urls import path

from . import views

app_name = "analytics_site"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("connections/<int:website_id>/add/", views.add_connection, name="add_connection"),
    path("connections/<int:pk>/delete/", views.delete_connection, name="delete_connection"),
]
