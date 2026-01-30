"""
URL configuration for analytics app.

Main analytics dashboard that shows platform-specific analytics apps.
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]
