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

from .models import MastodonPost, MastodonEngagementSummary
from mastodon_native.models import MastodonAccount


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
    most_engaged_post = MastodonPost.objects.filter(
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
        'current_sort': sort_by,
        # Platform-specific configuration
        'platform_name': 'Mastodon',
        'platform_namespace': 'analytics_mastodon',
        'top_post': most_engaged_post,
        'post_card_template': 'analytics_mastodon/partials/post_card.html#post-card',
        # Engagement metrics with generic names
        'engagement_metrics': {
            'metric1': total_engagement['total_favourites'] or 0,
            'metric2': total_engagement['total_replies'] or 0,
            'metric3': total_engagement['total_reblogs'] or 0,
        },
        # Engagement labels
        'engagement_labels': {
            'metric1': 'favourites',
            'metric1_plural': 'Favourites',
            'metric2': 'replies',
            'metric2_plural': 'Replies',
            'metric3': 'reblogs',
            'metric3_plural': 'Reblogs',
        },
        # Engagement keys for accessing engagement_summary attributes
        'engagement_keys': {
            'metric1': 'total_favourites',
            'metric2': 'total_replies',
            'metric3': 'total_reblogs',
        },
        # Sort keys for URL parameters
        'sort_keys': {
            'metric1': 'favourites',
            'metric2': 'replies',
            'metric3': 'reblogs',
        },
        # Legacy context for backward compatibility (if needed elsewhere)
        'total_favourites': total_engagement['total_favourites'] or 0,
        'total_replies': total_engagement['total_replies'] or 0,
        'total_reblogs': total_engagement['total_reblogs'] or 0,
        'total_engagement_count': total_engagement['total_engagement'] or 0,
        'most_engaged_post': most_engaged_post,
    }

    # For HTMX requests, return just the content without the base template
    template = 'analytics_mastodon/dashboard.html'
    if request.htmx:
        template = 'analytics/platform_dashboard_content.html'

    return render(request, template, context)


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

    context = {
        'active_page': 'analytics',
        'post': post,
        'favourites': favourites,
        'replies': replies,
        'reblogs': reblogs,
        'engagement_timeline': engagement_timeline,
    }

    # For HTMX requests, return just the content without the base template
    template = 'analytics_mastodon/post_detail.html'
    if request.htmx:
        template = 'analytics_mastodon/post_detail_content.html'

    return render(request, template, context)


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
        context = {'message': f'Error refreshing post: {str(e)}'}
        return render(request, 'analytics_mastodon/partials/toast.html#toast-error', context)


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
        context = {'message': f'Synced {created + updated} posts ({created} new, {updated} updated)'}
        response = render(request, 'analytics_mastodon/partials/toast.html#toast-success', context)

        # Trigger HTMX event to refresh the dashboard
        response['HX-Trigger'] = 'postsUpdated'

        return response

    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'message': f'Error syncing posts: {str(e)}'}
        return render(request, 'analytics_mastodon/partials/toast.html#toast-error', context)


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
            'message': f'Engagement fetch started for @{account.username}. This may take a few minutes...'
        }
        return render(request, 'analytics_mastodon/partials/toast.html#toast-info', context)

    except Exception as e:
        logger.error(f"Error enqueueing engagement fetch for account {account_id}: {e}", exc_info=True)

        # Return error toast partial
        context = {'message': f'Error starting engagement fetch: {str(e)}'}
        return render(request, 'analytics_mastodon/partials/toast.html#toast-error', context)


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
