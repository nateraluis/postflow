from django.urls import path

from . import views

app_name = "glass"

urlpatterns = [
    path("", views.manual_queue, name="queue"),
    path("accounts/add/", views.add_account, name="add_account"),
    path("accounts/<int:pk>/delete/", views.delete_account, name="delete_account"),
    path("tasks/<int:pk>/done/", views.mark_posted, name="mark_posted"),
    path("tasks/<int:pk>/skip/", views.skip_task, name="skip_task"),
]
