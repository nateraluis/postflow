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
from analytics.utils import get_base_analytics_context


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

    # Calculate engagement distribution for widget
    total_engagement_sum = (total_engagement['total_likes'] or 0) + (total_engagement['total_comments'] or 0) + (total_engagement['total_saved'] or 0)
    if total_engagement_sum > 0:
        engagement_distribution = {
            'total_likes': total_engagement['total_likes'] or 0,
            'total_comments': total_engagement['total_comments'] or 0,
            'total_shares': total_engagement['total_saved'] or 0,  # Map saved to shares
            'total_engagement': total_engagement_sum,
            'likes_percentage': round(((total_engagement['total_likes'] or 0) / total_engagement_sum) * 100, 2),
            'comments_percentage': round(((total_engagement['total_comments'] or 0) / total_engagement_sum) * 100, 2),
            'shares_percentage': round(((total_engagement['total_saved'] or 0) / total_engagement_sum) * 100, 2),
            'has_data': True,
        }
    else:
        engagement_distribution = {'has_data': False}

    # Get base context from utility function
    context = get_base_analytics_context(request, 'instagram')

    # Add view-specific context
    context.update({
        'active_page': 'analytics',
        'posts': posts,
        'user_accounts': user_accounts,
        'total_posts': total_posts,
        'top_post': top_post,
        'total_likes': total_engagement['total_likes'] or 0,
        'total_comments': total_engagement['total_comments'] or 0,
        'total_saved': total_engagement['total_saved'] or 0,
        'total_reach': total_engagement['total_reach'] or 0,
        'engagement_data': engagement_distribution,
    })

    return render(request, 'analytics/shared/dashboard.html', context)


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

    # Get base context from utility function
    context = get_base_analytics_context(request, 'instagram')

    # Add view-specific context
    context.update({
        'active_page': 'analytics',
        'post': post,
        'top_level_comments': top_level_comments,
        'replies': replies,
    })

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

        # Return success toast partial
        context = {
            'status': 'success',
            'message': f'Synced {created + updated} posts ({created} new, {updated} updated)'
        }
        return render(request, 'analytics/shared/partials/toast.html', context)

    except Exception as e:
        # Return error toast partial
        context = {
            'status': 'error',
            'message': f'Error syncing posts: {str(e)}'
        }
        return render(request, 'analytics/shared/partials/toast.html', context)


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

        # Return success toast partial
        context = {
            'status': 'info',
            'message': f'Insights fetch started for @{account.username}. This may take a few minutes...'
        }
        return render(request, 'analytics/shared/partials/toast.html', context)

    except Exception as e:
        # Return error toast partial
        context = {
            'status': 'error',
            'message': f'Error starting insights fetch: {str(e)}'
        }
        return render(request, 'analytics/shared/partials/toast.html', context)


@login_required
def engagement_distribution(request):
    """
    Display engagement type distribution for Instagram.

    Shows donut chart visualization of engagement patterns. Note: Instagram
    provides likes/comments/saved metrics (no individual engagement data).
    """
    # Get user's Instagram Business accounts
    user_accounts = InstagramBusinessAccount.objects.filter(user=request.user)

    # Aggregate engagement totals from all user posts
    engagement_totals = InstagramEngagementSummary.objects.filter(
        post__account__in=user_accounts
    ).aggregate(
        total_likes=Sum('total_likes'),
        total_comments=Sum('total_comments'),
        total_saved=Sum('total_saved'),
        total_engagement=Sum('total_engagement')
    )

    # Handle None values (no data case)
    total_likes = engagement_totals['total_likes'] or 0
    total_comments = engagement_totals['total_comments'] or 0
    total_shares = engagement_totals['total_saved'] or 0  # Map saved to shares for consistency
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

    # Get base context from utility function
    context = get_base_analytics_context(request, 'instagram')

    # Add view-specific context
    context.update({
        'total_likes': total_likes,
        'total_comments': total_comments,
        'total_shares': total_shares,  # Actually "saved" for Instagram
        'total_engagement': total_engagement,
        'likes_percentage': likes_percentage,
        'comments_percentage': comments_percentage,
        'shares_percentage': shares_percentage,
        'accounts': user_accounts,
        'has_data': total_engagement > 0,
    })

    return render(request, 'analytics/shared/engagement_distribution.html', context)
