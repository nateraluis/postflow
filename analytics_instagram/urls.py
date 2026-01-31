"""
URL routing for Instagram Analytics.
"""
from django.urls import path
from . import views

app_name = 'analytics_instagram'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/refresh/', views.refresh_post, name='refresh_post'),
    path('account/<int:account_id>/sync/', views.sync_account, name='sync_account'),
    path('account/<int:account_id>/fetch-insights/', views.fetch_insights, name='fetch_insights'),
]
