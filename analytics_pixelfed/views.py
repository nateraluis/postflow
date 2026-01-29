"""
Views for Pixelfed Analytics dashboard.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Q, F, Value
from django.db.models.functions import Coalesce
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

    # Get sort parameter (default: most recent)
    sort_by = request.GET.get('sort', 'recent')

    # Build base query for posts
    posts_query = PixelfedPost.objects.filter(
        account__in=user_accounts
    ).select_related(
        'account',
        'engagement_summary'
    ).prefetch_related(
        'likes',
        'comments',
        'shares'
    )

    # Apply sorting - for engagement metrics, we need to handle NULL engagement_summary
    if sort_by == 'likes':
        # Annotate with coalesced values to handle posts without engagement_summary
        posts = posts_query.annotate(
            likes_sort=Coalesce(F('engagement_summary__total_likes'), Value(0))
        ).order_by('-likes_sort', '-posted_at')[:50]
    elif sort_by == 'comments':
        posts = posts_query.annotate(
            comments_sort=Coalesce(F('engagement_summary__total_comments'), Value(0))
        ).order_by('-comments_sort', '-posted_at')[:50]
    elif sort_by == 'shares':
        posts = posts_query.annotate(
            shares_sort=Coalesce(F('engagement_summary__total_shares'), Value(0))
        ).order_by('-shares_sort', '-posted_at')[:50]
    elif sort_by == 'engagement':
        posts = posts_query.annotate(
            engagement_sort=Coalesce(F('engagement_summary__total_engagement'), Value(0))
        ).order_by('-engagement_sort', '-posted_at')[:50]
    else:  # 'recent' or default
        posts = posts_query.order_by('-posted_at')[:50]

    # Calculate summary statistics
    total_posts = PixelfedPost.objects.filter(account__in=user_accounts).count()
    total_engagement = PixelfedEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_likes=Sum('total_likes'),
        total_comments=Sum('total_comments'),
        total_shares=Sum('total_shares'),
        total_engagement=Sum('total_engagement')
    )

    # Get top performing post (by total engagement)
    most_liked_post = PixelfedPost.objects.filter(
        account__in=user_accounts,
        engagement_summary__isnull=False,
        engagement_summary__total_engagement__gt=0
    ).select_related(
        'account',
        'engagement_summary'
    ).order_by('-engagement_summary__total_engagement', '-posted_at').first()

    context = {
        'active_page': 'analytics',
        'posts': posts,
        'user_accounts': user_accounts,
        'total_posts': total_posts,
        'total_likes': total_engagement['total_likes'] or 0,
        'total_comments': total_engagement['total_comments'] or 0,
        'total_shares': total_engagement['total_shares'] or 0,
        'total_engagement_count': total_engagement['total_engagement'] or 0,
        'most_liked_post': most_liked_post,
        'current_sort': sort_by,
    }

    # For HTMX requests, return just the content without the base template
    template = 'analytics_pixelfed/dashboard.html'
    if request.htmx:
        template = 'analytics_pixelfed/dashboard_content.html'

    return render(request, template, context)


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

    # For HTMX requests, return just the content without the base template
    template = 'analytics_pixelfed/post_detail.html'
    if request.htmx:
        template = 'analytics_pixelfed/post_detail_content.html'

    return render(request, template, context)


@login_required
@require_http_methods(["POST"])
def refresh_post(request, post_id):
    """
    Manually refresh engagement metrics for a specific post.
    Triggers a page reload via HX-Redirect to show updated data.
    """
    from django.http import HttpResponse
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

        # Return HX-Redirect header to reload the page with HTMX
        response = HttpResponse()
        response['HX-Redirect'] = request.path
        return response

    except Exception as e:
        logger.error(f"Error refreshing post {post_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'message': f'Error refreshing post: {str(e)}'}
        return render(request, 'analytics_pixelfed/partials/toast.html#toast-error', context)


@login_required
@require_http_methods(["POST"])
def sync_account(request, account_id):
    """
    Manually sync posts from a Pixelfed account.
    Returns a toast notification partial and triggers a refresh event.
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

        # Sync posts (no engagement fetching - that's done separately)
        fetcher = PixelfedAnalyticsFetcher(account)
        created, updated = fetcher.sync_account_posts(limit=100)  # Fetch up to 100 posts (3 API calls)

        logger.info(f"Synced account {account_id}: {created} created, {updated} updated")

        # Return success toast partial with HX-Trigger to refresh posts
        context = {'message': f'Synced {created + updated} posts ({created} new, {updated} updated)'}
        response = render(request, 'analytics_pixelfed/partials/toast.html#toast-success', context)

        # Trigger HTMX event to refresh the dashboard
        response['HX-Trigger'] = 'postsUpdated'

        return response

    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'message': f'Error syncing posts: {str(e)}'}
        return render(request, 'analytics_pixelfed/partials/toast.html#toast-error', context)


@login_required
@require_http_methods(["POST"])
def fetch_engagement(request, account_id):
    """
    Trigger background task to fetch engagement for an account's posts.
    """
    from .tasks import fetch_account_engagement
    import logging

    logger = logging.getLogger('postflow')

    try:
        account = get_object_or_404(
            MastodonAccount,
            pk=account_id,
            user=request.user,
            instance_url__icontains='pixelfed'
        )

        # Enqueue background task to fetch engagement
        task = fetch_account_engagement.enqueue(account_id=account_id, limit_posts=50)

        logger.info(f"Enqueued engagement fetch task for account {account_id}: task_id={task.id}")

        # Return success toast partial
        context = {
            'message': f'Engagement fetch started for @{account.username}. This may take a few minutes...'
        }
        return render(request, 'analytics_pixelfed/partials/toast.html#toast-info', context)

    except Exception as e:
        logger.error(f"Error enqueueing engagement fetch for account {account_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'message': f'Error starting engagement fetch: {str(e)}'}
        return render(request, 'analytics_pixelfed/partials/toast.html#toast-error', context)


@login_required
def post_list_partial(request):
    """
    Returns just the post list partial for HTMX refreshes.
    Used to update the post list without reloading the entire page.
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

    context = {
        'posts': posts,
    }

    return render(request, 'analytics_pixelfed/partials/post_list.html', context)


@login_required
def stats_partial(request):
    """
    Returns just the summary statistics partial for HTMX refreshes.
    """
    # Get user's Pixelfed accounts
    user_accounts = MastodonAccount.objects.filter(
        user=request.user,
        instance_url__icontains='pixelfed'
    )

    # Get all posts for user's accounts
    posts = PixelfedPost.objects.filter(
        account__in=user_accounts
    )

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

    context = {
        'total_posts': total_posts,
        'total_likes': total_engagement['total_likes'] or 0,
        'total_comments': total_engagement['total_comments'] or 0,
        'total_shares': total_engagement['total_shares'] or 0,
        'total_engagement': total_engagement['total_engagement'] or 0,
    }

    return render(request, 'analytics_pixelfed/partials/stats.html', context)


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
