"""
URL configuration for analytics app.
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.analytics_dashboard, name='dashboard'),
    path('refresh/', views.refresh_analytics, name='refresh'),
    path('sync/', views.sync_posts, name='sync'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
]
