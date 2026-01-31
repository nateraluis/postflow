"""
Views for Instagram Analytics dashboard.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Q, F, Value
from django.db.models.functions import Coalesce
from datetime import timedelta
from django.utils import timezone

from .models import InstagramPost, InstagramEngagementSummary, InstagramComment
from instagram.models import InstagramBusinessAccount
from .fetcher import InstagramAnalyticsFetcher
from .tasks import fetch_account_insights


@login_required
def dashboard(request):
    """
    Main Instagram analytics dashboard showing posts and engagement metrics.
    """
    # Get user's Instagram Business accounts
    user_accounts = InstagramBusinessAccount.objects.filter(user=request.user)

    # Get sort parameter (default: most recent)
    sort_by = request.GET.get('sort', 'recent')

    # Build base query for posts
    posts_query = InstagramPost.objects.filter(
        account__in=user_accounts
    ).select_related(
        'account',
        'engagement_summary'
    ).prefetch_related(
        'comments'
    )

    # Apply sorting
    if sort_by == 'likes':
        posts = posts_query.annotate(
            likes_sort=Coalesce(F('engagement_summary__total_likes'), Value(0))
        ).order_by('-likes_sort', '-posted_at')[:50]
    elif sort_by == 'comments':
        posts = posts_query.annotate(
            comments_sort=Coalesce(F('engagement_summary__total_comments'), Value(0))
        ).order_by('-comments_sort', '-posted_at')[:50]
    elif sort_by == 'saved':
        posts = posts_query.annotate(
            saved_sort=Coalesce(F('engagement_summary__total_saved'), Value(0))
        ).order_by('-saved_sort', '-posted_at')[:50]
    elif sort_by == 'engagement':
        posts = posts_query.annotate(
            engagement_sort=Coalesce(F('engagement_summary__total_engagement'), Value(0))
        ).order_by('-engagement_sort', '-posted_at')[:50]
    elif sort_by == 'reach':
        posts = posts_query.annotate(
            reach_sort=Coalesce(F('engagement_summary__total_reach'), Value(0))
        ).order_by('-reach_sort', '-posted_at')[:50]
    elif sort_by == 'impressions':
        posts = posts_query.annotate(
            impressions_sort=Coalesce(F('engagement_summary__total_impressions'), Value(0))
        ).order_by('-impressions_sort', '-posted_at')[:50]
    else:  # 'recent' or default
        posts = posts_query.order_by('-posted_at')[:50]

    # Calculate summary statistics
    total_posts = InstagramPost.objects.filter(account__in=user_accounts).count()
    total_engagement = InstagramEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_likes=Sum('total_likes'),
        total_comments=Sum('total_comments'),
        total_saved=Sum('total_saved'),
        total_reach=Sum('total_reach'),
        total_impressions=Sum('total_impressions'),
        total_engagement=Sum('total_engagement')
    )

    # Get top performing post (by total engagement)
    # Try to get post with engagement summary first, fallback to any post
    top_post = InstagramPost.objects.filter(
        account__in=user_accounts,
        engagement_summary__isnull=False
    ).select_related(
        'account',
        'engagement_summary'
    ).order_by('-engagement_summary__total_engagement', '-posted_at').first()

    # If no post with engagement summary, get most recent post
    if not top_post:
        top_post = InstagramPost.objects.filter(
            account__in=user_accounts
        ).select_related('account').order_by('-posted_at').first()

    context = {
        'active_page': 'analytics',
        'posts': posts,
        'user_accounts': user_accounts,
        'total_posts': total_posts,
        'current_sort': sort_by,
        # Platform-specific configuration
        'platform_name': 'Instagram',
        'platform_namespace': 'analytics_instagram',
        'top_post': top_post,
        # Engagement metrics
        'engagement_metrics': {
            'metric1': total_engagement['total_likes'] or 0,
            'metric2': total_engagement['total_comments'] or 0,
            'metric3': total_engagement['total_saved'] or 0,
            'metric4': total_engagement['total_reach'] or 0,
            'metric5': total_engagement['total_impressions'] or 0,
            'metric1_label': 'Likes',
            'metric2_label': 'Comments',
            'metric3_label': 'Saved',
            'metric4_label': 'Reach',
            'metric5_label': 'Impressions',
        },
        'sort_options': [
            {'value': 'recent', 'label': 'Most Recent'},
            {'value': 'likes', 'label': 'Most Likes'},
            {'value': 'comments', 'label': 'Most Comments'},
            {'value': 'saved', 'label': 'Most Saved'},
            {'value': 'engagement', 'label': 'Most Engagement'},
            {'value': 'reach', 'label': 'Most Reach'},
            {'value': 'impressions', 'label': 'Most Impressions'},
        ]
    }

    # For HTMX requests, return just the content without the base template
    template = 'analytics_instagram/dashboard.html'
    if request.htmx:
        template = 'analytics/platform_dashboard_content.html'

    return render(request, template, context)


@login_required
def post_detail(request, post_id):
    """
    Detailed view of a single Instagram post with engagement metrics.
    """
    post = get_object_or_404(
        InstagramPost.objects.select_related('account', 'engagement_summary'),
        id=post_id,
        account__user=request.user
    )

    # Get comments ordered chronologically for conversation flow
    comments = post.comments.order_by('timestamp')

    # Separate top-level comments and replies
    top_level_comments = comments.filter(parent_comment_id__isnull=True)
    replies = comments.filter(parent_comment_id__isnull=False)

    context = {
        'active_page': 'analytics',
        'post': post,
        'top_level_comments': top_level_comments,
        'replies': replies,
        'platform_name': 'Instagram',
        'platform_namespace': 'analytics_instagram',
    }

    return render(request, 'analytics_instagram/post_detail.html', context)


@login_required
@require_http_methods(['POST'])
def refresh_post(request, post_id):
    """
    Manually refresh insights for a specific post.
    """
    post = get_object_or_404(
        InstagramPost.objects.select_related('account'),
        id=post_id,
        account__user=request.user
    )

    try:
        fetcher = InstagramAnalyticsFetcher(post.account)

        # Fetch insights
        insights = fetcher.fetch_post_insights(post)

        # Fetch comments
        new_comments = fetcher.fetch_post_comments(post)

        # Redirect back to post detail page
        return redirect('analytics_instagram:post_detail', post_id=post.id)

    except Exception as e:
        # On error, redirect back with error message (could enhance with messages framework)
        return redirect('analytics_instagram:post_detail', post_id=post.id)


@login_required
@require_http_methods(['POST'])
def sync_account(request, account_id):
    """
    Manually sync posts from an Instagram Business account.
    """
    account = get_object_or_404(
        InstagramBusinessAccount,
        id=account_id,
        user=request.user
    )

    try:
        fetcher = InstagramAnalyticsFetcher(account)
        created, updated = fetcher.sync_account_posts(limit=50)

        return JsonResponse({
            'status': 'success',
            'message': f'Synced: {created} new posts, {updated} updated',
            'created': created,
            'updated': updated
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(['POST'])
def fetch_insights(request, account_id):
    """
    Enqueue background task to fetch insights for an account.
    """
    account = get_object_or_404(
        InstagramBusinessAccount,
        id=account_id,
        user=request.user
    )

    try:
        # Enqueue background task
        fetch_account_insights.enqueue(account_id=account.id, limit_posts=50)

        return JsonResponse({
            'status': 'success',
            'message': f'Insights fetch started for @{account.username}'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
