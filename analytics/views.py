"""
Analytics views - Placeholder for migration to platform-specific apps.

Legacy analytics functionality has been moved to platform-specific apps:
- Pixelfed: analytics_pixelfed
- Instagram: (future)
- Mastodon: (future)
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


@login_required
def dashboard(request):
    """
    Placeholder dashboard that redirects to Pixelfed analytics.
    """
    # Redirect to Pixelfed analytics for now
    return redirect('analytics_pixelfed:dashboard')


@login_required
def legacy_redirect(request):
    """
    Catch-all for old analytics URLs - redirect to new structure.
    """
    return redirect('analytics_pixelfed:dashboard')
