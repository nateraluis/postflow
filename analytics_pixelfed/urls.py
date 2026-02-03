"""
URL configuration for Pixelfed Analytics.
"""
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'analytics_pixelfed'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Redirect top-engagers to engagement-distribution (unified view)
    path('top-engagers/', RedirectView.as_view(pattern_name='analytics_pixelfed:engagement_distribution', permanent=True), name='top_engagers'),
    path('engagement-distribution/', views.engagement_distribution, name='engagement_distribution'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/refresh/', views.refresh_post, name='refresh_post'),
    path('account/<int:account_id>/sync/', views.sync_account, name='sync_account'),
    path('account/<int:account_id>/fetch-engagement/', views.fetch_engagement, name='fetch_engagement'),
    # Partial refresh endpoints
    path('partials/posts/', views.post_list_partial, name='post_list_partial'),
    path('partials/stats/', views.stats_partial, name='stats_partial'),
]
