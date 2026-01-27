"""
Views for Pixelfed Analytics dashboard.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Q
from datetime import timedelta
from django.utils import timezone

from .models import PixelfedPost, PixelfedEngagementSummary
from pixelfed.models import MastodonAccount


@login_required
def dashboard(request):
    """
    Main Pixelfed analytics dashboard showing posts and engagement metrics.
    """
    # Get user's Pixelfed accounts
    user_accounts = MastodonAccount.objects.filter(
        user=request.user,
        instance_url__icontains='pixelfed'
    )

    # Get all posts for user's accounts, ordered by most recent
    posts = PixelfedPost.objects.filter(
        account__in=user_accounts
    ).select_related(
        'account',
        'engagement_summary'
    ).prefetch_related(
        'likes',
        'comments',
        'shares'
    ).order_by('-posted_at')[:50]  # Last 50 posts

    # Calculate summary statistics
    total_posts = posts.count()
    total_engagement = PixelfedEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_likes=Sum('total_likes'),
        total_comments=Sum('total_comments'),
        total_shares=Sum('total_shares'),
        total_engagement=Sum('total_engagement')
    )

    # Get top performing posts (by total engagement)
    top_posts = PixelfedPost.objects.filter(
        account__in=user_accounts
    ).select_related(
        'engagement_summary'
    ).order_by('-engagement_summary__total_engagement')[:10]

    context = {
        'active_page': 'analytics',
        'posts': posts,
        'user_accounts': user_accounts,
        'total_posts': total_posts,
        'total_likes': total_engagement['total_likes'] or 0,
        'total_comments': total_engagement['total_comments'] or 0,
        'total_shares': total_engagement['total_shares'] or 0,
        'total_engagement': total_engagement['total_engagement'] or 0,
        'top_posts': top_posts,
    }

    return render(request, 'analytics_pixelfed/dashboard.html', context)


@login_required
def post_detail(request, post_id):
    """
    Detailed view of a single post with engagement timeline.
    """
    # Get the post
    post = get_object_or_404(
        PixelfedPost,
        pk=post_id,
        account__user=request.user
    )

    # Get engagement data
    likes = post.likes.select_related('post').order_by('-liked_at')
    comments = post.comments.select_related('post').order_by('commented_at')
    shares = post.shares.select_related('post').order_by('-shared_at')

    # Get engagement over time (for chart)
    engagement_timeline = _get_engagement_timeline(post)

    context = {
        'active_page': 'analytics',
        'post': post,
        'likes': likes,
        'comments': comments,
        'shares': shares,
        'engagement_timeline': engagement_timeline,
    }

    return render(request, 'analytics_pixelfed/post_detail.html', context)


@login_required
@require_http_methods(["POST"])
def refresh_post(request, post_id):
    """
    Manually refresh engagement metrics for a specific post.
    """
    from .fetcher import PixelfedAnalyticsFetcher
    import logging

    logger = logging.getLogger('postflow')

    try:
        post = get_object_or_404(
            PixelfedPost,
            pk=post_id,
            account__user=request.user
        )

        # Fetch updated engagement
        fetcher = PixelfedAnalyticsFetcher(post.account)
        stats = fetcher.fetch_post_engagement(post)

        logger.info(f"Refreshed engagement for post {post_id}: {stats}")

        return JsonResponse({
            'status': 'success',
            'message': 'Engagement metrics refreshed successfully',
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Error refreshing post {post_id}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def sync_account(request, account_id):
    """
    Manually sync posts from a Pixelfed account.
    """
    from .fetcher import PixelfedAnalyticsFetcher
    import logging

    logger = logging.getLogger('postflow')

    try:
        account = get_object_or_404(
            MastodonAccount,
            pk=account_id,
            user=request.user,
            instance_url__icontains='pixelfed'
        )

        # Sync posts
        fetcher = PixelfedAnalyticsFetcher(account)
        created, updated = fetcher.sync_account_posts(limit=50)

        logger.info(f"Synced account {account_id}: {created} created, {updated} updated")

        return JsonResponse({
            'status': 'success',
            'message': f'Synced {created + updated} posts ({created} new, {updated} updated)',
            'created': created,
            'updated': updated
        })

    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def _get_engagement_timeline(post):
    """
    Helper function to generate engagement timeline data for charts.

    Returns data in format suitable for Chart.js.
    """
    # Get all engagement events with timestamps
    likes_data = list(post.likes.values_list('liked_at', flat=True))
    comments_data = list(post.comments.values_list('commented_at', flat=True))
    shares_data = list(post.shares.values_list('shared_at', flat=True))

    # Group by day
    timeline = {}

    for like_time in likes_data:
        day = like_time.date()
        if day not in timeline:
            timeline[day] = {'likes': 0, 'comments': 0, 'shares': 0}
        timeline[day]['likes'] += 1

    for comment_time in comments_data:
        day = comment_time.date()
        if day not in timeline:
            timeline[day] = {'likes': 0, 'comments': 0, 'shares': 0}
        timeline[day]['comments'] += 1

    for share_time in shares_data:
        day = share_time.date()
        if day not in timeline:
            timeline[day] = {'likes': 0, 'comments': 0, 'shares': 0}
        timeline[day]['shares'] += 1

    # Convert to sorted list of dicts for Chart.js
    sorted_timeline = [
        {
            'date': str(day),
            'likes': data['likes'],
            'comments': data['comments'],
            'shares': data['shares'],
            'total': data['likes'] + data['comments'] + data['shares']
        }
        for day, data in sorted(timeline.items())
    ]

    return sorted_timeline
