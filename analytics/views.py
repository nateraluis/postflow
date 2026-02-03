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
from analytics.utils import get_posting_calendar_data


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
