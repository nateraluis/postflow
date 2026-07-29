from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    path("queue/", views.review_queue, name="queue"),
    path("promote/<int:blog_post_id>/", views.promote_form, name="promote_form"),
    path("promote/<int:blog_post_id>/generate/", views.promote, name="promote"),
    path("drafts/<int:pk>/approve/", views.approve_draft, name="approve"),
    path("drafts/<int:pk>/discard/", views.discard_draft, name="discard"),
    path("drafts/<int:pk>/regenerate/", views.regenerate_draft, name="regenerate"),
]
