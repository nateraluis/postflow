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

    # Deduplicate posts with the same caption and similar post date (within 1 hour)
    # This handles synced posts that are the same content across platforms
    from datetime import timedelta
    deduplicated_posts = []
    seen_captions = {}

    for post in posts:
        caption_key = (post.caption or '').strip()[:100]  # Use first 100 chars as key

        if not caption_key:
            # Posts without captions are always included
            deduplicated_posts.append(post)
            continue

        # Check if we've seen a similar post
        found_duplicate = False
        for seen_caption, (seen_post, seen_date) in seen_captions.items():
            # Check if captions match and dates are within 1 hour
            time_diff = abs((post.post_date - seen_date).total_seconds())
            if caption_key == seen_caption and time_diff < 3600:
                # Merge this post's accounts into the existing post
                seen_post.instagram_accounts_list = list(seen_post.instagram_accounts.all())
                seen_post.mastodon_accounts_list = list(seen_post.mastodon_accounts.all())
                seen_post.mastodon_native_accounts_list = list(seen_post.mastodon_native_accounts.all())

                # Add new accounts from duplicate post
                seen_post.instagram_accounts_list.extend(list(post.instagram_accounts.all()))
                seen_post.mastodon_accounts_list.extend(list(post.mastodon_accounts.all()))
                seen_post.mastodon_native_accounts_list.extend(list(post.mastodon_native_accounts.all()))

                # Merge analytics
                seen_post.analytics_list = list(seen_post.analytics.all())
                seen_post.analytics_list.extend(list(post.analytics.all()))

                found_duplicate = True
                break

        if not found_duplicate:
            # First time seeing this caption
            seen_captions[caption_key] = (post, post.post_date)
            deduplicated_posts.append(post)

    posts = deduplicated_posts

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
        'total_posts': len(posts),
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
@require_http_methods(["POST"])
def sync_posts(request):
    """
    Manually trigger sync of posts from all connected social media accounts.

    Returns JSON response with status.
    """
    import logging
    logger = logging.getLogger('postflow')

    logger.info(f"Post sync requested by user {request.user.email}")

    try:
        logger.info("Starting sync of all social media posts")
        call_command('sync_all_posts', limit=50)
        message = 'Successfully synced posts from all connected accounts'
        logger.info(f"Successfully synced posts for user {request.user.email}")
    except Exception as e:
        logger.exception(f"Error syncing posts: {e}")
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
