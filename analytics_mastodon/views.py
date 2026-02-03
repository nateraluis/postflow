"""
Views for Mastodon Analytics dashboard.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Q, F, Value
from django.db.models.functions import Coalesce
from datetime import timedelta
from django.utils import timezone
from collections import defaultdict

from .models import MastodonPost, MastodonEngagementSummary
from mastodon_native.models import MastodonAccount
from analytics.utils import get_base_analytics_context, get_posting_calendar_data


@login_required
def dashboard(request):
    """
    Main Mastodon analytics dashboard showing posts and engagement metrics.
    """
    # Get user's Mastodon accounts (from mastodon_native table)
    user_accounts = MastodonAccount.objects.filter(
        user=request.user
    )

    # Get sort parameter (default: most recent)
    sort_by = request.GET.get('sort', 'recent')

    # Build base query for posts
    posts_query = MastodonPost.objects.filter(
        account__in=user_accounts
    ).select_related(
        'account',
        'engagement_summary'
    ).prefetch_related(
        'favourites',
        'replies',
        'reblogs'
    )

    # Apply sorting - for engagement metrics, we need to handle NULL engagement_summary
    if sort_by == 'favourites':
        # Annotate with coalesced values to handle posts without engagement_summary
        posts = posts_query.annotate(
            favourites_sort=Coalesce(F('engagement_summary__total_favourites'), Value(0))
        ).order_by('-favourites_sort', '-posted_at')[:50]
    elif sort_by == 'replies':
        posts = posts_query.annotate(
            replies_sort=Coalesce(F('engagement_summary__total_replies'), Value(0))
        ).order_by('-replies_sort', '-posted_at')[:50]
    elif sort_by == 'reblogs':
        posts = posts_query.annotate(
            reblogs_sort=Coalesce(F('engagement_summary__total_reblogs'), Value(0))
        ).order_by('-reblogs_sort', '-posted_at')[:50]
    elif sort_by == 'engagement':
        posts = posts_query.annotate(
            engagement_sort=Coalesce(F('engagement_summary__total_engagement'), Value(0))
        ).order_by('-engagement_sort', '-posted_at')[:50]
    else:  # 'recent' or default
        posts = posts_query.order_by('-posted_at')[:50]

    # Calculate summary statistics
    total_posts = MastodonPost.objects.filter(account__in=user_accounts).count()
    total_engagement = MastodonEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_favourites=Sum('total_favourites'),
        total_replies=Sum('total_replies'),
        total_reblogs=Sum('total_reblogs'),
        total_engagement=Sum('total_engagement')
    )

    # Get top performing post (by total engagement)
    top_post = MastodonPost.objects.filter(
        account__in=user_accounts,
        engagement_summary__isnull=False,
        engagement_summary__total_engagement__gt=0
    ).select_related(
        'account',
        'engagement_summary'
    ).order_by('-engagement_summary__total_engagement', '-posted_at').first()

    # Get top 3 engagers
    from collections import defaultdict
    user_posts = MastodonPost.objects.filter(account__in=user_accounts)

    # Exclude own usernames from top engagers
    exclude_usernames = list(user_accounts.values_list('username', flat=True))

    # Aggregate engagement by user
    engagement_scores = defaultdict(lambda: {'favourites': 0, 'replies': 0, 'reblogs': 0})

    # Count favourites
    from .models import MastodonFavourite, MastodonReply, MastodonReblog
    favourites = MastodonFavourite.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(
        favourite_count=Count('id')
    )
    for fav in favourites:
        engagement_scores[fav['username']]['favourites'] = fav['favourite_count']

    # Count replies
    replies = MastodonReply.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(
        reply_count=Count('id')
    )
    for reply in replies:
        engagement_scores[reply['username']]['replies'] = reply['reply_count']

    # Count reblogs
    reblogs = MastodonReblog.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(
        reblog_count=Count('id')
    )
    for reblog in reblogs:
        engagement_scores[reblog['username']]['reblogs'] = reblog['reblog_count']

    # Calculate weighted engagement scores and format for template
    top_engagers_list = []
    for username, scores in engagement_scores.items():
        total_interactions = scores['favourites'] + scores['replies'] + scores['reblogs']
        # Weighted scoring: Comments 3x, Reblogs 2x, Favourites 1x
        weighted_score = scores['favourites'] + (scores['replies'] * 3) + (scores['reblogs'] * 2)

        top_engagers_list.append({
            'username': username,
            'likes': scores['favourites'],
            'comments': scores['replies'],
            'shares': scores['reblogs'],
            'total_interactions': total_interactions,
            'engagement_score': weighted_score,
        })

    # Sort by engagement score and take top 3
    top_engagers_list = sorted(top_engagers_list, key=lambda x: x['engagement_score'], reverse=True)[:3]

    # Calculate engagement distribution for widget
    total_engagement_sum = (total_engagement['total_favourites'] or 0) + (total_engagement['total_replies'] or 0) + (total_engagement['total_reblogs'] or 0)
    if total_engagement_sum > 0:
        engagement_distribution = {
            'total_likes': total_engagement['total_favourites'] or 0,
            'total_comments': total_engagement['total_replies'] or 0,
            'total_shares': total_engagement['total_reblogs'] or 0,
            'total_engagement': total_engagement_sum,
            'likes_percentage': round(((total_engagement['total_favourites'] or 0) / total_engagement_sum) * 100, 2),
            'comments_percentage': round(((total_engagement['total_replies'] or 0) / total_engagement_sum) * 100, 2),
            'shares_percentage': round(((total_engagement['total_reblogs'] or 0) / total_engagement_sum) * 100, 2),
            'has_data': True,
        }
    else:
        engagement_distribution = {'has_data': False}

    # Get posting calendar data (Mastodon only)
    calendar_data = None
    if user_accounts.exists():
        calendar_data = get_posting_calendar_data(request.user, platform='mastodon', days=365)

    # Get base context from utility function
    context = get_base_analytics_context(request, 'mastodon')

    # Add view-specific context
    context.update({
        'active_page': 'analytics',
        'posts': posts,
        'user_accounts': user_accounts,
        'total_posts': total_posts,
        'top_post': top_post,
        'total_favourites': total_engagement['total_favourites'] or 0,
        'total_replies': total_engagement['total_replies'] or 0,
        'total_reblogs': total_engagement['total_reblogs'] or 0,
        'top_engagers': top_engagers_list,
        'engagement_data': engagement_distribution,
        'calendar_data': calendar_data,
    })

    return render(request, 'analytics/shared/dashboard.html', context)


@login_required
def post_detail(request, post_id):
    """
    Detailed view of a single post with engagement timeline.
    """
    # Get the post
    post = get_object_or_404(
        MastodonPost,
        pk=post_id,
        account__user=request.user
    )

    # Get engagement data
    favourites = post.favourites.select_related('post').order_by('-favourited_at')
    replies = post.replies.select_related('post').order_by('replied_at')
    reblogs = post.reblogs.select_related('post').order_by('-reblogged_at')

    # Get engagement over time (for chart)
    engagement_timeline = _get_engagement_timeline(post)

    # Get base context from utility function
    context = get_base_analytics_context(request, 'mastodon')

    # Add view-specific context
    context.update({
        'active_page': 'analytics',
        'post': post,
        'favourites': favourites,
        'replies': replies,
        'reblogs': reblogs,
        'engagement_timeline': engagement_timeline,
    })

    # Use platform-specific template that extends shared base
    return render(request, 'analytics_mastodon/post_detail.html', context)


@login_required
@require_http_methods(["POST"])
def refresh_post(request, post_id):
    """
    Manually refresh engagement metrics for a specific post.
    Triggers a page reload via HX-Redirect to show updated data.
    """
    from django.http import HttpResponse
    from .fetcher import MastodonAnalyticsFetcher
    import logging

    logger = logging.getLogger('postflow')

    try:
        post = get_object_or_404(
            MastodonPost,
            pk=post_id,
            account__user=request.user
        )

        # Fetch updated engagement
        fetcher = MastodonAnalyticsFetcher(post.account)
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
    Manually sync posts from a Mastodon account.
    Returns a toast notification partial and triggers a refresh event.
    """
    from .fetcher import MastodonAnalyticsFetcher
    import logging

    logger = logging.getLogger('postflow')

    try:
        account = get_object_or_404(
            MastodonAccount,
            pk=account_id,
            user=request.user
        )

        # Sync posts (no engagement fetching - that's done separately)
        fetcher = MastodonAnalyticsFetcher(account)
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
            user=request.user
        )

        # Enqueue background task to fetch engagement
        task = fetch_account_engagement.enqueue(account_id=account_id, limit_posts=50)

        logger.info(f"Enqueued engagement fetch task for account {account_id}: task_id={task.id}")

        # Return success toast partial
        context = {
            'status': 'info', 'message': f'Engagement fetch started for @{account.username}. This may take a few minutes...'
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
    # Get user's Mastodon accounts (from mastodon_native table)
    user_accounts = MastodonAccount.objects.filter(
        user=request.user
    )

    # Get all posts for user's accounts, ordered by most recent
    posts = MastodonPost.objects.filter(
        account__in=user_accounts
    ).select_related(
        'account',
        'engagement_summary'
    ).prefetch_related(
        'favourites',
        'replies',
        'reblogs'
    ).order_by('-posted_at')[:50]  # Last 50 posts

    context = {
        'posts': posts,
    }

    return render(request, 'analytics_mastodon/partials/post_list.html', context)


@login_required
def stats_partial(request):
    """
    Returns just the summary statistics partial for HTMX refreshes.
    """
    # Get user's Mastodon accounts (from mastodon_native table)
    user_accounts = MastodonAccount.objects.filter(
        user=request.user
    )

    # Get all posts for user's accounts
    posts = MastodonPost.objects.filter(
        account__in=user_accounts
    )

    # Calculate summary statistics
    total_posts = posts.count()
    total_engagement = MastodonEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_favourites=Sum('total_favourites'),
        total_replies=Sum('total_replies'),
        total_reblogs=Sum('total_reblogs'),
        total_engagement=Sum('total_engagement')
    )

    context = {
        'total_posts': total_posts,
        'total_favourites': total_engagement['total_favourites'] or 0,
        'total_replies': total_engagement['total_replies'] or 0,
        'total_reblogs': total_engagement['total_reblogs'] or 0,
        'total_engagement': total_engagement['total_engagement'] or 0,
    }

    return render(request, 'analytics_mastodon/partials/stats.html', context)


@login_required
def engagement_distribution(request):
    """
    Display engagement type distribution (favourites vs replies vs reblogs) with top engagers.

    Shows donut chart visualization of engagement patterns and table of top engagers
    to help understand audience behavior and engagement preferences.
    """
    # Get user's Mastodon accounts
    user_accounts = MastodonAccount.objects.filter(user=request.user)

    # Aggregate engagement totals from all user posts
    engagement_totals = MastodonEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_favourites=Sum('total_favourites'),
        total_replies=Sum('total_replies'),
        total_reblogs=Sum('total_reblogs'),
        total_engagement=Sum('total_engagement')
    )

    # Handle None values (no data case)
    total_likes = engagement_totals['total_favourites'] or 0
    total_comments = engagement_totals['total_replies'] or 0
    total_shares = engagement_totals['total_reblogs'] or 0
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
    user_posts = MastodonPost.objects.filter(account__in=user_accounts)
    exclude_usernames = list(user_accounts.values_list('username', flat=True))

    from .models import MastodonFavourite, MastodonReply, MastodonReblog
    engagement_scores = defaultdict(lambda: {'favourites': 0, 'replies': 0, 'reblogs': 0})

    # Count favourites
    favourites = MastodonFavourite.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(favourite_count=Count('id'))
    for fav in favourites:
        engagement_scores[fav['username']]['favourites'] = fav['favourite_count']

    # Count replies
    replies = MastodonReply.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(reply_count=Count('id'))
    for reply in replies:
        engagement_scores[reply['username']]['replies'] = reply['reply_count']

    # Count reblogs
    reblogs = MastodonReblog.objects.filter(
        post__in=user_posts
    ).exclude(username__in=exclude_usernames).values('username').annotate(reblog_count=Count('id'))
    for reblog in reblogs:
        engagement_scores[reblog['username']]['reblogs'] = reblog['reblog_count']

    # Calculate weighted engagement scores
    top_engagers_list = []
    for username, scores in engagement_scores.items():
        total_interactions = scores['favourites'] + scores['replies'] + scores['reblogs']
        weighted_score = scores['favourites'] + (scores['replies'] * 3) + (scores['reblogs'] * 2)

        top_engagers_list.append({
            'username': username,
            'likes': scores['favourites'],
            'comments': scores['replies'],
            'shares': scores['reblogs'],
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
    context = get_base_analytics_context(request, 'mastodon')

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


def _get_engagement_timeline(post):
    """
    Helper function to generate engagement timeline data for charts.

    Returns data in format suitable for Chart.js.
    """
    # Get all engagement events with timestamps
    favourites_data = list(post.favourites.values_list('favourited_at', flat=True))
    replies_data = list(post.replies.values_list('replied_at', flat=True))
    reblogs_data = list(post.reblogs.values_list('reblogged_at', flat=True))

    # Group by day
    timeline = {}

    for fav_time in favourites_data:
        day = fav_time.date()
        if day not in timeline:
            timeline[day] = {'favourites': 0, 'replies': 0, 'reblogs': 0}
        timeline[day]['favourites'] += 1

    for reply_time in replies_data:
        day = reply_time.date()
        if day not in timeline:
            timeline[day] = {'favourites': 0, 'replies': 0, 'reblogs': 0}
        timeline[day]['replies'] += 1

    for reblog_time in reblogs_data:
        day = reblog_time.date()
        if day not in timeline:
            timeline[day] = {'favourites': 0, 'replies': 0, 'reblogs': 0}
        timeline[day]['reblogs'] += 1

    # Convert to sorted list of dicts for Chart.js
    sorted_timeline = [
        {
            'date': str(day),
            'favourites': data['favourites'],
            'replies': data['replies'],
            'reblogs': data['reblogs'],
            'total': data['favourites'] + data['replies'] + data['reblogs']
        }
        for day, data in sorted(timeline.items())
    ]

    return sorted_timeline
