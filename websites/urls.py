from django.urls import path

from . import views

app_name = "websites"

urlpatterns = [
    path("", views.website_list, name="list"),
    path("add/", views.website_add, name="add"),
    path("<int:pk>/", views.website_detail, name="detail"),
    path("<int:pk>/sync/", views.website_sync, name="sync"),
    path("<int:pk>/api-key/", views.website_add_api_key, name="add_api_key"),
    path("<int:pk>/delete/", views.website_delete, name="delete"),
]
