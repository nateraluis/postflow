"""
Views for analytics dashboard.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch
from django.core.management import call_command
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from postflow.models import ScheduledPost
from .models import PostAnalytics


@login_required
def analytics_dashboard(request):
    """
    Display analytics dashboard showing posted content with engagement metrics.

    Filters:
    - platform: Filter by platform (instagram, mastodon, pixelfed)
    - days: Show posts from last N days (7, 30, 90)
    """
    from postflow.utils import get_s3_signed_url

    # Get filter parameters
    platform_filter = request.GET.get('platform', 'all')
    days_filter = request.GET.get('days', '30')

    # Get user's posted posts with analytics
    posts = ScheduledPost.objects.filter(
        user=request.user,
        status='posted'
    ).prefetch_related(
        Prefetch(
            'analytics',
            queryset=PostAnalytics.objects.select_related('scheduled_post')
        ),
        'instagram_accounts',
        'mastodon_accounts',
        'mastodon_native_accounts',
        'images',  # Prefetch PostImage for multi-image posts
    ).order_by('-post_date')

    # Apply platform filter
    if platform_filter != 'all':
        posts = posts.filter(
            analytics__platform=platform_filter
        ).distinct()

    # Apply days filter (optional date range filtering)
    # This can be added later if needed

    # Generate signed URLs for images in each post
    for post in posts:
        # Check for PostImage records (new multi-image posts)
        if post.images.exists():
            first_image = post.images.first()
            post.image_url = get_s3_signed_url(first_image.image.name, expiration=7200)  # 2 hour expiration
        # Fallback to legacy single image field
        elif post.image:
            post.image_url = get_s3_signed_url(post.image.name, expiration=7200)
        else:
            post.image_url = None

    # Prepare context
    context = {
        'active_page': 'analytics',
        'posts': posts,
        'platform_filter': platform_filter,
        'days_filter': days_filter,
        'total_posts': posts.count(),
    }

    # Check if HTMX request
    if request.headers.get('HX-Request'):
        return render(request, 'analytics/dashboard.html', context)

    return render(request, 'analytics/dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def refresh_analytics(request):
    """
    Manually trigger analytics refresh for user's recent posts.

    Returns JSON response with status.
    """
    import logging
    logger = logging.getLogger('postflow')

    logger.info(f"Analytics refresh requested by user {request.user.email}")

    # Get post_id if provided
    post_id = request.POST.get('post_id')

    if post_id:
        # Refresh specific post (raises 404 if not found)
        post = get_object_or_404(ScheduledPost, id=post_id, user=request.user)
        try:
            logger.info(f"Fetching analytics for post {post_id}")
            call_command('fetch_analytics', post_id=post_id, force=True)
            message = f'Analytics refreshed for post {post_id}'
            logger.info(f"Successfully refreshed analytics for post {post_id}")
        except Exception as e:
            logger.exception(f"Error refreshing analytics for post {post_id}: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    else:
        # Refresh all recent posts (last 7 days)
        try:
            logger.info("Fetching analytics for last 7 days")
            call_command('fetch_analytics', days=7, force=True)
            message = 'Analytics refreshed for recent posts'
            logger.info("Successfully refreshed analytics for recent posts")
        except Exception as e:
            logger.exception(f"Error refreshing analytics: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({
        'status': 'success',
        'message': message
    })


@login_required
def post_detail(request, post_id):
    """
    Display detailed analytics for a single post.

    Shows breakdown by platform and historical data.
    """
    post = get_object_or_404(
        ScheduledPost,
        id=post_id,
        user=request.user,
        status='posted'
    )

    analytics = PostAnalytics.objects.filter(
        scheduled_post=post
    ).select_related('scheduled_post').order_by('-last_updated')

    context = {
        'active_page': 'analytics',
        'post': post,
        'analytics': analytics,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'analytics/post_detail.html', context)

    return render(request, 'analytics/post_detail.html', context)
