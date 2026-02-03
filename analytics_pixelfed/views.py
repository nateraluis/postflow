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

from .models import PixelfedPost, PixelfedEngagementSummary, PixelfedLike, PixelfedComment, PixelfedShare
from pixelfed.models import MastodonAccount
from analytics.utils import get_base_analytics_context
from collections import defaultdict


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
    top_post = PixelfedPost.objects.filter(
        account__in=user_accounts,
        engagement_summary__isnull=False,
        engagement_summary__total_engagement__gt=0
    ).select_related(
        'account',
        'engagement_summary'
    ).order_by('-engagement_summary__total_engagement', '-posted_at').first()

    # Get top 3 engagers
    exclude_usernames = list(user_accounts.values_list('username', flat=True))
    user_posts = PixelfedPost.objects.filter(account__in=user_accounts)

    engagement_scores = defaultdict(lambda: {'likes': 0, 'comments': 0, 'shares': 0})

    # Count likes
    likes_data = PixelfedLike.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(count=Count('id'))
    for item in likes_data:
        engagement_scores[item['username']]['likes'] = item['count']

    # Count comments (weighted 3x)
    comments_data = PixelfedComment.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(count=Count('id'))
    for item in comments_data:
        engagement_scores[item['username']]['comments'] = item['count']

    # Count shares (weighted 2x)
    shares_data = PixelfedShare.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(count=Count('id'))
    for item in shares_data:
        engagement_scores[item['username']]['shares'] = item['count']

    # Calculate top 3 engagers
    top_engagers_list = []
    for username, scores in engagement_scores.items():
        weighted_score = scores['likes'] + (scores['comments'] * 3) + (scores['shares'] * 2)
        total_interactions = scores['likes'] + scores['comments'] + scores['shares']

        top_engagers_list.append({
            'username': username,
            'likes': scores['likes'],
            'comments': scores['comments'],
            'shares': scores['shares'],
            'total_interactions': total_interactions,
            'engagement_score': weighted_score,
        })

    top_engagers_list = sorted(top_engagers_list, key=lambda x: x['engagement_score'], reverse=True)[:3]

    # Calculate engagement distribution for widget
    total_engagement_sum = (total_engagement['total_likes'] or 0) + (total_engagement['total_comments'] or 0) + (total_engagement['total_shares'] or 0)
    if total_engagement_sum > 0:
        engagement_distribution = {
            'total_likes': total_engagement['total_likes'] or 0,
            'total_comments': total_engagement['total_comments'] or 0,
            'total_shares': total_engagement['total_shares'] or 0,
            'total_engagement': total_engagement_sum,
            'likes_percentage': round(((total_engagement['total_likes'] or 0) / total_engagement_sum) * 100, 2),
            'comments_percentage': round(((total_engagement['total_comments'] or 0) / total_engagement_sum) * 100, 2),
            'shares_percentage': round(((total_engagement['total_shares'] or 0) / total_engagement_sum) * 100, 2),
            'has_data': True,
        }
    else:
        engagement_distribution = {'has_data': False}

    # Get base context from utility function
    context = get_base_analytics_context(request, 'pixelfed')

    # Add view-specific context
    context.update({
        'active_page': 'analytics',
        'posts': posts,
        'user_accounts': user_accounts,
        'total_posts': total_posts,
        'top_post': top_post,
        'total_likes': total_engagement['total_likes'] or 0,
        'total_comments': total_engagement['total_comments'] or 0,
        'total_shares': total_engagement['total_shares'] or 0,
        'top_engagers': top_engagers_list,
        'engagement_data': engagement_distribution,
    })

    return render(request, 'analytics/shared/dashboard.html', context)


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

    # Get base context from utility function
    context = get_base_analytics_context(request, 'pixelfed')

    # Add view-specific context
    context.update({
        'active_page': 'analytics',
        'post': post,
        'likes': likes,
        'comments': comments,
        'shares': shares,
        'engagement_timeline': engagement_timeline,
    })

    # Use platform-specific template that extends shared base
    return render(request, 'analytics_pixelfed/post_detail.html', context)


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
        context = {'status': 'error', 'message': f'Error refreshing post: {str(e)}'}
        return render(request, 'analytics/shared/partials/toast.html', context)


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
        created, updated = fetcher.sync_account_posts(limit=None)  # Fetch all posts

        logger.info(f"Synced account {account_id}: {created} created, {updated} updated")

        # Return success toast partial with HX-Trigger to refresh posts
        context = {'status': 'success', 'message': f'Synced {created + updated} posts ({created} new, {updated} updated)'}
        response = render(request, 'analytics/shared/partials/toast.html', context)

        # Trigger HTMX event to refresh the dashboard
        response['HX-Trigger'] = 'postsUpdated'

        return response

    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'status': 'error', 'message': f'Error syncing posts: {str(e)}'}
        return render(request, 'analytics/shared/partials/toast.html', context)


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
            'status': 'info',
            'message': f'Engagement fetch started for @{account.username}. This may take a few minutes...'
        }
        return render(request, 'analytics/shared/partials/toast.html', context)

    except Exception as e:
        logger.error(f"Error enqueueing engagement fetch for account {account_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'status': 'error', 'message': f'Error starting engagement fetch: {str(e)}'}
        return render(request, 'analytics/shared/partials/toast.html', context)


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


@login_required
def engagement_distribution(request):
    """
    Display engagement type distribution (likes vs comments vs shares) with top engagers.

    Shows donut chart visualization of engagement patterns and table of top engagers
    to help understand audience behavior and engagement preferences.
    """
    # Get user's Pixelfed accounts
    user_accounts = MastodonAccount.objects.filter(
        user=request.user,
        instance_url__icontains='pixelfed'
    )

    # Aggregate engagement totals from all user posts
    engagement_totals = PixelfedEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_likes=Sum('total_likes'),
        total_comments=Sum('total_comments'),
        total_shares=Sum('total_shares'),
        total_engagement=Sum('total_engagement')
    )

    # Handle None values (no data case)
    total_likes = engagement_totals['total_likes'] or 0
    total_comments = engagement_totals['total_comments'] or 0
    total_shares = engagement_totals['total_shares'] or 0
    total_engagement = engagement_totals['total_engagement'] or 0

    # Calculate percentages (avoid division by zero)
    if total_engagement > 0:
        likes_percentage = round((total_likes / total_engagement) * 100, 2)
        comments_percentage = round((total_comments / total_engagement) * 100, 2)
        shares_percentage = round((total_shares / total_engagement) * 100, 2)
    else:
        likes_percentage = 0
        comments_percentage = 0
        shares_percentage = 0

    # Calculate top engagers (same logic as top_engagers view)
    exclude_usernames = list(user_accounts.values_list('username', flat=True))
    user_posts = PixelfedPost.objects.filter(account__in=user_accounts)

    engagement_scores = defaultdict(lambda: {'likes': 0, 'comments': 0, 'shares': 0, 'total': 0})

    # Count likes
    likes_data = PixelfedLike.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(count=Count('id'))
    for item in likes_data:
        engagement_scores[item['username']]['likes'] = item['count']

    # Count comments (weighted 3x)
    comments_data = PixelfedComment.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(count=Count('id'))
    for item in comments_data:
        engagement_scores[item['username']]['comments'] = item['count']

    # Count shares (weighted 2x)
    shares_data = PixelfedShare.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(count=Count('id'))
    for item in shares_data:
        engagement_scores[item['username']]['shares'] = item['count']

    # Calculate weighted total engagement score
    top_engagers_list = []
    for username, scores in engagement_scores.items():
        weighted_score = scores['likes'] + (scores['comments'] * 3) + (scores['shares'] * 2)
        total_interactions = scores['likes'] + scores['comments'] + scores['shares']

        top_engagers_list.append({
            'username': username,
            'likes': scores['likes'],
            'comments': scores['comments'],
            'shares': scores['shares'],
            'total_interactions': total_interactions,
            'engagement_score': weighted_score,
        })

    # Handle sorting from query parameters
    sort_by = request.GET.get('sort', 'engagement_score')
    sort_order = request.GET.get('order', 'desc')

    # Define valid sort fields
    valid_sort_fields = ['likes', 'comments', 'shares', 'total_interactions', 'engagement_score', 'username']
    if sort_by not in valid_sort_fields:
        sort_by = 'engagement_score'

    # Sort the engagers list
    reverse_sort = (sort_order == 'desc')
    if sort_by == 'username':
        top_engagers_list = sorted(top_engagers_list, key=lambda x: x[sort_by].lower(), reverse=reverse_sort)
    else:
        top_engagers_list = sorted(top_engagers_list, key=lambda x: x[sort_by], reverse=reverse_sort)

    # Limit to top 50
    top_engagers_list = top_engagers_list[:50]

    # Get base context from utility function
    context = get_base_analytics_context(request, 'pixelfed')

    # Add view-specific context
    context.update({
        'total_likes': total_likes,
        'total_comments': total_comments,
        'total_shares': total_shares,
        'total_engagement': total_engagement,
        'likes_percentage': likes_percentage,
        'comments_percentage': comments_percentage,
        'shares_percentage': shares_percentage,
        'accounts': user_accounts,
        'has_data': total_engagement > 0,
        'top_engagers': top_engagers_list,
        'sort_by': sort_by,
        'sort_order': sort_order,
    })

    # If HTMX request, return the table with headers (so indicators update)
    if request.headers.get('HX-Request'):
        return render(request, 'analytics/shared/partials/engagers_table.html', context)

    return render(request, 'analytics/shared/engagement_distribution.html', context)
