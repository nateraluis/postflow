"""
URL routing for Instagram Analytics.
"""
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'analytics_instagram'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Redirect top-engagers to engagement-distribution (unified view)
    path('top-engagers/', RedirectView.as_view(pattern_name='analytics_instagram:engagement_distribution', permanent=True), name='top_engagers'),
    path('engagement-distribution/', views.engagement_distribution, name='engagement_distribution'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/refresh/', views.refresh_post, name='refresh_post'),
    path('account/<int:account_id>/sync/', views.sync_account, name='sync_account'),
    path('account/<int:account_id>/fetch-insights/', views.fetch_insights, name='fetch_insights'),
]
