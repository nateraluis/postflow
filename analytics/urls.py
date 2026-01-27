"""
URL configuration for analytics app.

Legacy analytics URLs redirect to platform-specific analytics apps.
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('refresh/', views.legacy_redirect, name='refresh'),
    path('sync/', views.legacy_redirect, name='sync'),
    path('post/<int:post_id>/', views.legacy_redirect, name='post_detail'),
]
