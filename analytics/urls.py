"""
URL configuration for analytics app.

Main analytics dashboard that shows platform-specific analytics apps.
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('best-times/', views.best_times_view, name='best_times'),
    path('best-times/api/', views.best_time_suggestion_api, name='best_time_api'),
    path('media-type/', views.media_type_view, name='media_type'),
    path('engagement-velocity/', views.engagement_velocity_view, name='engagement_velocity'),
    path('hashtag-performance/', views.hashtag_performance_view, name='hashtag_performance'),
    path('comments/', views.comments_inbox, name='comments_inbox'),
    path('comments/reply/', views.reply_comment, name='reply_comment'),
]
