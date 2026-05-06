"""
Analytics views - Platform selector and overview.

Platform-specific analytics:
- Pixelfed: analytics_pixelfed
- Mastodon: analytics_mastodon
- Instagram: analytics_instagram
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from pixelfed.models import MastodonAccount as PixelfedMastodonAccount
from mastodon_native.models import MastodonAccount as MastodonNativeAccount
from instagram.models import InstagramBusinessAccount
from analytics_pixelfed.models import PixelfedPost, PixelfedEngagementSummary
from analytics_mastodon.models import MastodonPost, MastodonEngagementSummary
from analytics_instagram.models import InstagramPost, InstagramEngagementSummary
from django.views.decorators.http import require_http_methods
from analytics.utils import (
    get_posting_calendar_data,
    get_best_posting_times,
    get_media_type_performance,
    get_engagement_velocity,
    get_hashtag_performance,
    get_top_performers,
    get_consistency_score,
    get_engagement_quality,
    get_growth_momentum,
    get_engagement_timeline,
    get_engagement_decay,
    get_caption_length_analysis,
    get_viral_coefficient,
    get_content_themes,
    get_conversation_threads,
)


@login_required
def dashboard(request):
    """
    Analytics dashboard with overview statistics for all platforms.
    """
    # Get user's Pixelfed accounts (from pixelfed app table)
    pixelfed_accounts = PixelfedMastodonAccount.objects.filter(
        user=request.user,
        instance_url__icontains='pixelfed'
    )

    # Get user's Mastodon accounts (from mastodon_native app table)
    mastodon_accounts = MastodonNativeAccount.objects.filter(
        user=request.user
    )

    # Get user's Instagram Business accounts
    instagram_accounts = InstagramBusinessAccount.objects.filter(
        user=request.user
    )

    # Calculate date ranges
    now = timezone.now()
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)

    # Pixelfed Statistics
    pixelfed_stats = None
    if pixelfed_accounts.exists():
        pixelfed_posts = PixelfedPost.objects.filter(account__in=pixelfed_accounts)
        pixelfed_posts_last_7 = pixelfed_posts.filter(posted_at__gte=last_7_days)

        # Get aggregate stats
        pixelfed_engagement = PixelfedEngagementSummary.objects.filter(
            post__account__in=pixelfed_accounts
        ).aggregate(
            total_likes=Sum('total_likes'),
            total_comments=Sum('total_comments'),
            total_shares=Sum('total_shares'),
            total_engagement=Sum('total_engagement')
        )

        # Get top post from last 7 days
        top_pixelfed_post = pixelfed_posts_last_7.select_related(
            'engagement_summary', 'account'
        ).filter(
            engagement_summary__isnull=False
        ).order_by('-engagement_summary__total_engagement').first()

        # Get recent activity (posts in last 7 days)
        recent_posts_count = pixelfed_posts_last_7.count()

        pixelfed_stats = {
            'total_posts': pixelfed_posts.count(),
            'posts_last_7_days': recent_posts_count,
            'total_likes': pixelfed_engagement['total_likes'] or 0,
            'total_comments': pixelfed_engagement['total_comments'] or 0,
            'total_shares': pixelfed_engagement['total_shares'] or 0,
            'total_engagement': pixelfed_engagement['total_engagement'] or 0,
            'top_post': top_pixelfed_post,
            'accounts': pixelfed_accounts,
        }

    # Mastodon Statistics
    mastodon_stats = None
    if mastodon_accounts.exists():
        mastodon_posts = MastodonPost.objects.filter(account__in=mastodon_accounts)
        mastodon_posts_last_7 = mastodon_posts.filter(posted_at__gte=last_7_days)

        # Get aggregate stats
        mastodon_engagement = MastodonEngagementSummary.objects.filter(
            post__account__in=mastodon_accounts
        ).aggregate(
            total_favourites=Sum('total_favourites'),
            total_replies=Sum('total_replies'),
            total_reblogs=Sum('total_reblogs'),
            total_engagement=Sum('total_engagement')
        )

        # Get top post from last 7 days
        top_mastodon_post = mastodon_posts_last_7.select_related(
            'engagement_summary', 'account'
        ).filter(
            engagement_summary__isnull=False
        ).order_by('-engagement_summary__total_engagement').first()

        # Get recent activity (posts in last 7 days)
        recent_posts_count = mastodon_posts_last_7.count()

        mastodon_stats = {
            'total_posts': mastodon_posts.count(),
            'posts_last_7_days': recent_posts_count,
            'total_favourites': mastodon_engagement['total_favourites'] or 0,
            'total_replies': mastodon_engagement['total_replies'] or 0,
            'total_reblogs': mastodon_engagement['total_reblogs'] or 0,
            'total_engagement': mastodon_engagement['total_engagement'] or 0,
            'top_post': top_mastodon_post,
            'accounts': mastodon_accounts,
        }

    # Instagram Statistics
    instagram_stats = None
    if instagram_accounts.exists():
        instagram_posts = InstagramPost.objects.filter(account__in=instagram_accounts)
        instagram_posts_last_7 = instagram_posts.filter(posted_at__gte=last_7_days)

        # Get aggregate stats
        instagram_engagement = InstagramEngagementSummary.objects.filter(
            post__account__in=instagram_accounts
        ).aggregate(
            total_likes=Sum('total_likes'),
            total_comments=Sum('total_comments'),
            total_saved=Sum('total_saved'),
            total_engagement=Sum('total_engagement')
        )

        # Get top post from last 7 days
        top_instagram_post = instagram_posts_last_7.select_related(
            'engagement_summary', 'account'
        ).filter(
            engagement_summary__isnull=False
        ).order_by('-engagement_summary__total_engagement').first()

        # Get recent activity (posts in last 7 days)
        recent_posts_count = instagram_posts_last_7.count()

        instagram_stats = {
            'total_posts': instagram_posts.count(),
            'posts_last_7_days': recent_posts_count,
            'total_likes': instagram_engagement['total_likes'] or 0,
            'total_comments': instagram_engagement['total_comments'] or 0,
            'total_saved': instagram_engagement['total_saved'] or 0,
            'total_engagement': instagram_engagement['total_engagement'] or 0,
            'top_post': top_instagram_post,
            'accounts': instagram_accounts,
        }

    # Get posting calendar data (all platforms)
    calendar_data = None
    if pixelfed_accounts.exists() or mastodon_accounts.exists() or instagram_accounts.exists():
        calendar_data = get_posting_calendar_data(request.user, platform=None, days=365)

    context = {
        'active_page': 'analytics',
        'pixelfed_accounts': pixelfed_accounts,
        'mastodon_accounts': mastodon_accounts,
        'instagram_accounts': instagram_accounts,
        'has_pixelfed': pixelfed_accounts.exists(),
        'has_mastodon': mastodon_accounts.exists(),
        'has_instagram': instagram_accounts.exists(),
        'pixelfed_stats': pixelfed_stats,
        'mastodon_stats': mastodon_stats,
        'instagram_stats': instagram_stats,
        'calendar_data': calendar_data,
    }

    if request.headers.get("HX-Request"):
        # Return both the content and sidebar with OOB swap
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, 'analytics/dashboard_content.html', context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)

    return render(request, 'analytics/dashboard.html', context)


@login_required
def best_times_view(request):
    """Best time to post analysis with heatmap."""
    days = int(request.GET.get('days', 90))
    data = get_best_posting_times(request.user, days=days)

    context = {
        'active_page': 'analytics',
        'best_times': data,
        'days': days,
    }

    if request.headers.get("HX-Request"):
        return render(request, 'analytics/best_times_content.html', context)
    return render(request, 'analytics/best_times.html', context)


@login_required
def best_time_suggestion_api(request):
    """API endpoint for time picker suggestion."""
    from django.http import JsonResponse
    data = get_best_posting_times(request.user, days=90)
    return JsonResponse({
        'suggestions': data['suggestions'],
        'use_benchmarks': data['use_benchmarks'],
    })


@login_required
def media_type_view(request):
    """Media type performance comparison."""
    days = int(request.GET.get('days', 90))
    data = get_media_type_performance(request.user, days=days)

    context = {
        'active_page': 'analytics',
        'media_data': data,
        'days': days,
    }

    if request.headers.get("HX-Request"):
        return render(request, 'analytics/media_type_content.html', context)
    return render(request, 'analytics/media_type.html', context)


@login_required
def engagement_velocity_view(request):
    """Engagement velocity chart."""
    days = int(request.GET.get('days', 90))
    data = get_engagement_velocity(request.user, days=days)

    context = {
        'active_page': 'analytics',
        'velocity_data': data,
        'days': days,
    }

    if request.headers.get("HX-Request"):
        return render(request, 'analytics/velocity_content.html', context)
    return render(request, 'analytics/velocity.html', context)


@login_required
def hashtag_performance_view(request):
    """Hashtag group performance analytics."""
    days = int(request.GET.get('days', 90))
    data = get_hashtag_performance(request.user, days=days)

    context = {
        'active_page': 'analytics',
        'hashtag_data': data,
        'days': days,
    }

    if request.headers.get("HX-Request"):
        return render(request, 'analytics/hashtag_performance_content.html', context)
    return render(request, 'analytics/hashtag_performance.html', context)


@login_required
def top_performers_view(request):
    """Top performing posts by engagement."""
    days = int(request.GET.get('days', 90))
    data = get_top_performers(request.user, days=days)
    context = {'active_page': 'analytics', 'performers_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/top_performers_content.html', context)
    return render(request, 'analytics/top_performers.html', context)


@login_required
def consistency_view(request):
    """Posting consistency score and streak."""
    days = int(request.GET.get('days', 90))
    data = get_consistency_score(request.user, days=days)
    context = {'active_page': 'analytics', 'consistency': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/consistency_content.html', context)
    return render(request, 'analytics/consistency.html', context)


@login_required
def quality_view(request):
    """Engagement quality score (weighted)."""
    days = int(request.GET.get('days', 90))
    data = get_engagement_quality(request.user, days=days)
    context = {'active_page': 'analytics', 'quality_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/quality_content.html', context)
    return render(request, 'analytics/quality.html', context)


@login_required
def growth_view(request):
    """Growth momentum dashboard."""
    days = int(request.GET.get('days', 90))
    data = get_growth_momentum(request.user, days=days)
    context = {'active_page': 'analytics', 'growth_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/growth_content.html', context)
    return render(request, 'analytics/growth.html', context)


@login_required
def timeline_view(request):
    """Enhanced engagement timeline with aggregation and CSV export."""
    days = int(request.GET.get('days', 90))
    agg = request.GET.get('agg', 'daily')
    data = get_engagement_timeline(request.user, days=days, aggregation=agg)

    # CSV download
    if request.GET.get('format') == 'csv':
        from django.http import HttpResponse as DjangoResponse
        response = DjangoResponse(data['csv'], content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="engagement_timeline.csv"'
        return response

    context = {'active_page': 'analytics', 'timeline_data': data, 'days': days, 'agg': agg}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/timeline_content.html', context)
    return render(request, 'analytics/timeline.html', context)


@login_required
def decay_view(request):
    """Engagement decay curve."""
    days = int(request.GET.get('days', 90))
    data = get_engagement_decay(request.user, days=days)
    context = {'active_page': 'analytics', 'decay_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/decay_content.html', context)
    return render(request, 'analytics/decay.html', context)


@login_required
def caption_length_view(request):
    """Caption length vs engagement analysis."""
    days = int(request.GET.get('days', 90))
    data = get_caption_length_analysis(request.user, days=days)
    context = {'active_page': 'analytics', 'caption_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/caption_length_content.html', context)
    return render(request, 'analytics/caption_length.html', context)


@login_required
def viral_view(request):
    """Viral coefficient tracker."""
    days = int(request.GET.get('days', 90))
    data = get_viral_coefficient(request.user, days=days)
    context = {'active_page': 'analytics', 'viral_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/viral_content.html', context)
    return render(request, 'analytics/viral.html', context)


@login_required
def themes_view(request):
    """Best performing content themes."""
    days = int(request.GET.get('days', 90))
    data = get_content_themes(request.user, days=days)
    context = {'active_page': 'analytics', 'themes_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/themes_content.html', context)
    return render(request, 'analytics/themes.html', context)


@login_required
def conversations_view(request):
    """Community conversation map."""
    days = int(request.GET.get('days', 30))
    data = get_conversation_threads(request.user, days=days)
    context = {'active_page': 'analytics', 'conversation_data': data, 'days': days}
    if request.headers.get("HX-Request"):
        return render(request, 'analytics/conversations_content.html', context)
    return render(request, 'analytics/conversations.html', context)


@login_required
def comments_inbox(request):
    """Unified comment inbox across all platforms."""
    from analytics_pixelfed.models import PixelfedComment
    from analytics_mastodon.models import MastodonReply

    days = int(request.GET.get('days', 7))
    cutoff = timezone.now() - timedelta(days=days)

    # Fetch Pixelfed comments
    pixelfed_accounts = PixelfedMastodonAccount.objects.filter(
        user=request.user, instance_url__icontains='pixelfed'
    )
    pixelfed_comments = []
    if pixelfed_accounts.exists():
        pixelfed_comments = list(
            PixelfedComment.objects.filter(
                post__account__in=pixelfed_accounts,
                commented_at__gte=cutoff,
            ).select_related('post', 'post__account').order_by('-commented_at')[:50]
        )

    # Fetch Mastodon replies
    mastodon_accounts = MastodonNativeAccount.objects.filter(user=request.user)
    mastodon_replies = []
    if mastodon_accounts.exists():
        mastodon_replies = list(
            MastodonReply.objects.filter(
                post__account__in=mastodon_accounts,
                replied_at__gte=cutoff,
            ).select_related('post', 'post__account').order_by('-replied_at')[:50]
        )

    # Merge into unified list
    comments = []
    for c in pixelfed_comments:
        comments.append({
            'platform': 'pixelfed',
            'username': c.username,
            'display_name': c.display_name or c.username,
            'content': c.content,
            'timestamp': c.commented_at,
            'post_caption': (c.post.caption or '')[:80],
            'post_url': c.post.post_url,
            'post_id': c.post.pixelfed_post_id,
            'comment_id': c.comment_id,
            'instance_url': c.post.instance_url,
            'is_recent': (timezone.now() - c.commented_at).total_seconds() < 3600,
        })
    for r in mastodon_replies:
        comments.append({
            'platform': 'mastodon',
            'username': r.username,
            'display_name': r.display_name or r.username,
            'content': r.content,
            'timestamp': r.replied_at,
            'post_caption': (r.post.content or '')[:80],
            'post_url': r.post.post_url,
            'post_id': r.post.mastodon_post_id,
            'comment_id': r.reply_id,
            'instance_url': r.post.instance_url,
            'is_recent': (timezone.now() - r.replied_at).total_seconds() < 3600,
        })

    # Sort by timestamp descending
    comments.sort(key=lambda x: x['timestamp'], reverse=True)

    context = {
        'active_page': 'comments',
        'comments': comments,
        'days': days,
        'total_comments': len(comments),
        'recent_count': sum(1 for c in comments if c['is_recent']),
    }

    if request.headers.get("HX-Request"):
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, 'analytics/comments_inbox_content.html', context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)
    return render(request, 'analytics/comments_inbox.html', context)


@login_required
@require_http_methods(["POST"])
def reply_comment(request):
    """Quick-reply to a comment via Mastodon/Pixelfed API."""
    from mastodon import Mastodon as MastodonClient
    import requests as http_requests

    platform = request.POST.get('platform')
    instance_url = request.POST.get('instance_url')
    comment_id = request.POST.get('comment_id')
    reply_text = request.POST.get('reply_text', '').strip()

    if not reply_text:
        return HttpResponse('<span class="text-red-500 text-xs">Reply cannot be empty</span>')

    try:
        if platform == 'mastodon':
            account = MastodonNativeAccount.objects.filter(
                user=request.user, instance_url=instance_url
            ).first()
            if account:
                client = MastodonClient(access_token=account.access_token, api_base_url=account.instance_url)
                client.status_post(status=reply_text, in_reply_to_id=comment_id, visibility="public")
                return HttpResponse('<span class="text-green-600 text-xs">Reply sent</span>')

        elif platform == 'pixelfed':
            account = PixelfedMastodonAccount.objects.filter(
                user=request.user, instance_url=instance_url
            ).first()
            if account:
                headers = {"Authorization": f"Bearer {account.access_token}", "Accept": "application/json"}
                url = f"{account.instance_url}/api/v1/statuses"
                data = {"status": reply_text, "in_reply_to_id": comment_id, "visibility": "public"}
                resp = http_requests.post(url, headers=headers, data=data, timeout=15)
                resp.raise_for_status()
                return HttpResponse('<span class="text-green-600 text-xs">Reply sent</span>')

        return HttpResponse('<span class="text-red-500 text-xs">Account not found</span>')
    except Exception as e:
        return HttpResponse(f'<span class="text-red-500 text-xs">Error: {str(e)[:50]}</span>')
