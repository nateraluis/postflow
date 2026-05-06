"""
Utility functions for analytics apps.
"""
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Q
from collections import defaultdict
import json


def get_platform_config(platform_slug):
    """
    Returns platform-specific configuration for analytics templates.

    Args:
        platform_slug: One of 'pixelfed', 'mastodon', 'instagram'

    Returns:
        Dictionary with platform configuration including metrics, colors, and labels
    """
    platforms = {
        'pixelfed': {
            'name': 'Pixelfed',
            'slug': 'pixelfed',
            'url_namespace': 'analytics_pixelfed',
            'metrics': [
                {
                    'key': 'likes',
                    'label': 'Likes',
                    'icon': 'heart',
                    'color': 'gray',
                    'db_field': 'total_likes'
                },
                {
                    'key': 'comments',
                    'label': 'Comments',
                    'icon': 'comment',
                    'color': 'gray',
                    'db_field': 'total_comments'
                },
                {
                    'key': 'shares',
                    'label': 'Shares',
                    'icon': 'share',
                    'color': 'gray',
                    'db_field': 'total_shares'
                },
            ],
            'sort_options': [
                {'value': 'recent', 'label': 'Most Recent'},
                {'value': 'engagement', 'label': 'Total Engagement'},
                {'value': 'likes', 'label': 'Most Likes'},
                {'value': 'comments', 'label': 'Most Comments'},
                {'value': 'shares', 'label': 'Most Shares'},
            ],
            'connect_url': 'accounts',
            'platform_label': 'Pixelfed',
        },
        'mastodon': {
            'name': 'Mastodon',
            'slug': 'mastodon',
            'url_namespace': 'analytics_mastodon',
            'metrics': [
                {
                    'key': 'favourites',
                    'label': 'Favourites',
                    'icon': 'heart',
                    'color': 'gray',
                    'db_field': 'total_favourites'
                },
                {
                    'key': 'replies',
                    'label': 'Replies',
                    'icon': 'comment',
                    'color': 'gray',
                    'db_field': 'total_replies'
                },
                {
                    'key': 'reblogs',
                    'label': 'Reblogs',
                    'icon': 'share',
                    'color': 'gray',
                    'db_field': 'total_reblogs'
                },
            ],
            'sort_options': [
                {'value': 'recent', 'label': 'Most Recent'},
                {'value': 'engagement', 'label': 'Total Engagement'},
                {'value': 'favourites', 'label': 'Most Favourites'},
                {'value': 'replies', 'label': 'Most Replies'},
                {'value': 'reblogs', 'label': 'Most Reblogs'},
            ],
            'connect_url': 'accounts',
            'platform_label': 'Mastodon',
        },
        'instagram': {
            'name': 'Instagram',
            'slug': 'instagram',
            'url_namespace': 'analytics_instagram',
            'metrics': [
                {
                    'key': 'likes',
                    'label': 'Likes',
                    'icon': 'heart',
                    'color': 'gray',
                    'db_field': 'total_likes'
                },
                {
                    'key': 'comments',
                    'label': 'Comments',
                    'icon': 'comment',
                    'color': 'gray',
                    'db_field': 'total_comments'
                },
                {
                    'key': 'saved',
                    'label': 'Saved',
                    'icon': 'bookmark',
                    'color': 'gray',
                    'db_field': 'total_saved'
                },
                {
                    'key': 'reach',
                    'label': 'Reach',
                    'icon': 'people',
                    'color': 'gray',
                    'db_field': 'total_reach'
                },
            ],
            'sort_options': [
                {'value': 'recent', 'label': 'Most Recent'},
                {'value': 'engagement', 'label': 'Total Engagement'},
                {'value': 'likes', 'label': 'Most Likes'},
                {'value': 'comments', 'label': 'Most Comments'},
                {'value': 'saved', 'label': 'Most Saved'},
                {'value': 'reach', 'label': 'Most Reach'},
                {'value': 'impressions', 'label': 'Most Impressions'},
            ],
            'connect_url': 'instagram:connect',
            'platform_label': 'Instagram Business',
        },
    }

    return platforms.get(platform_slug, platforms['pixelfed'])


def get_base_analytics_context(request, platform_slug):
    """
    Returns standardized context for analytics templates.

    Args:
        request: Django request object
        platform_slug: One of 'pixelfed', 'mastodon', 'instagram'

    Returns:
        Dictionary with base context for analytics templates
    """
    platform_config = get_platform_config(platform_slug)

    return {
        'platform': platform_config,
        'current_sort': request.GET.get('sort', 'recent'),
    }


def get_best_posting_times(user, days=90):
    """
    Analyze historical engagement to find optimal posting times.
    Returns a 7x24 heatmap (day_of_week x hour) with average engagement.
    Falls back to 2026 benchmarks if insufficient data.

    Args:
        user: Django User object
        days: Number of days to analyze (default: 90)

    Returns:
        Dictionary with heatmap data, best times, and suggestion text
    """
    from analytics_pixelfed.models import PixelfedPost, PixelfedEngagementSummary
    from analytics_mastodon.models import MastodonPost, MastodonEngagementSummary
    from analytics_instagram.models import InstagramPost, InstagramEngagementSummary
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount
    from instagram.models import InstagramBusinessAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    # Collect (day_of_week, hour) -> [engagement_values]
    time_engagement = defaultdict(list)

    # Pixelfed posts
    pixelfed_accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if pixelfed_accounts.exists():
        posts = PixelfedPost.objects.filter(
            account__in=pixelfed_accounts,
            posted_at__gte=start_date,
        ).select_related('engagement_summary')
        for post in posts:
            eng = post.engagement_summary.total_engagement if hasattr(post, 'engagement_summary') and post.engagement_summary else 0
            dow = post.posted_at.weekday()  # 0=Monday
            hour = post.posted_at.hour
            time_engagement[(dow, hour)].append(eng)

    # Mastodon posts
    mastodon_accounts = MastodonNativeAccount.objects.filter(user=user)
    if mastodon_accounts.exists():
        posts = MastodonPost.objects.filter(
            account__in=mastodon_accounts,
            posted_at__gte=start_date,
        ).select_related('engagement_summary')
        for post in posts:
            eng = post.engagement_summary.total_engagement if hasattr(post, 'engagement_summary') and post.engagement_summary else 0
            dow = post.posted_at.weekday()
            hour = post.posted_at.hour
            time_engagement[(dow, hour)].append(eng)

    # Instagram posts
    instagram_accounts = InstagramBusinessAccount.objects.filter(user=user)
    if instagram_accounts.exists():
        posts = InstagramPost.objects.filter(
            account__in=instagram_accounts,
            posted_at__gte=start_date,
        ).select_related('engagement_summary')
        for post in posts:
            eng = post.engagement_summary.total_engagement if hasattr(post, 'engagement_summary') and post.engagement_summary else 0
            dow = post.posted_at.weekday()
            hour = post.posted_at.hour
            time_engagement[(dow, hour)].append(eng)

    # Build heatmap
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    heatmap = []
    best_slots = []

    total_data_points = sum(len(v) for v in time_engagement.values())

    for dow in range(7):
        row = []
        for hour in range(24):
            values = time_engagement.get((dow, hour), [])
            avg = sum(values) / len(values) if values else 0
            row.append({
                'day': dow,
                'hour': hour,
                'avg_engagement': round(avg, 1),
                'post_count': len(values),
            })
            if values:
                best_slots.append((avg, dow, hour))
        heatmap.append({'day_name': day_names[dow], 'hours': row})

    # Sort to find best times
    best_slots.sort(reverse=True)
    top_3 = best_slots[:3]

    # Fallback to benchmarks if insufficient data (<10 posts)
    use_benchmarks = total_data_points < 10
    if use_benchmarks:
        suggestions = [
            {'day': 'Wednesday', 'hour': 9, 'note': '2026 benchmark'},
            {'day': 'Thursday', 'hour': 12, 'note': '2026 benchmark'},
            {'day': 'Wednesday', 'hour': 18, 'note': '2026 benchmark'},
        ]
    else:
        suggestions = [
            {
                'day': day_names[s[1]],
                'hour': s[2],
                'avg_engagement': s[0],
                'note': 'from your data',
            }
            for s in top_3
        ]

    return {
        'heatmap': heatmap,
        'suggestions': suggestions,
        'use_benchmarks': use_benchmarks,
        'total_posts_analyzed': total_data_points,
        'days_analyzed': days,
    }


def get_media_type_performance(user, days=90):
    """
    Compare engagement by media type (image/video/carousel).

    Returns:
        Dictionary with per-type averages and totals
    """
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'types': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts,
        posted_at__gte=start_date,
    ).select_related('engagement_summary')

    type_stats = defaultdict(lambda: {'count': 0, 'total_engagement': 0, 'total_likes': 0, 'total_comments': 0, 'total_shares': 0})

    for post in posts:
        mt = post.media_type or 'image'
        eng = post.engagement_summary if hasattr(post, 'engagement_summary') and post.engagement_summary else None
        type_stats[mt]['count'] += 1
        if eng:
            type_stats[mt]['total_engagement'] += eng.total_engagement or 0
            type_stats[mt]['total_likes'] += eng.total_likes or 0
            type_stats[mt]['total_comments'] += eng.total_comments or 0
            type_stats[mt]['total_shares'] += eng.total_shares or 0

    types = []
    for mt, stats in type_stats.items():
        avg = stats['total_engagement'] / stats['count'] if stats['count'] > 0 else 0
        types.append({
            'type': mt,
            'label': mt.title(),
            'count': stats['count'],
            'total_engagement': stats['total_engagement'],
            'avg_engagement': round(avg, 1),
            'total_likes': stats['total_likes'],
            'total_comments': stats['total_comments'],
            'total_shares': stats['total_shares'],
        })

    types.sort(key=lambda x: x['avg_engagement'], reverse=True)

    return {'types': types, 'has_data': len(types) > 0}


def get_engagement_velocity(user, days=90, hours_window=72):
    """
    Calculate how fast posts gain engagement in the first N hours.
    Compares 'fast starters' vs 'slow burners'.

    Returns:
        Dictionary with velocity data per post
    """
    from analytics_pixelfed.models import PixelfedPost, PixelfedLike
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'posts': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts,
        posted_at__gte=start_date,
    ).select_related('engagement_summary').order_by('-posted_at')[:20]

    velocity_data = []
    for post in posts:
        # Count likes in first 24h, 48h, 72h based on first_seen_at
        likes_24h = post.likes.filter(
            first_seen_at__lte=post.posted_at + timedelta(hours=24)
        ).count()
        likes_48h = post.likes.filter(
            first_seen_at__lte=post.posted_at + timedelta(hours=48)
        ).count()
        likes_72h = post.likes.filter(
            first_seen_at__lte=post.posted_at + timedelta(hours=72)
        ).count()

        total = post.engagement_summary.total_engagement if hasattr(post, 'engagement_summary') and post.engagement_summary else 0

        velocity_data.append({
            'post_id': post.id,
            'caption_preview': (post.caption[:60] + '...') if post.caption and len(post.caption) > 60 else (post.caption or ''),
            'posted_at': post.posted_at.isoformat(),
            'likes_24h': likes_24h,
            'likes_48h': likes_48h,
            'likes_72h': likes_72h,
            'total_engagement': total,
            'velocity_score': likes_24h / max(total, 1) * 100,  # % of total in first 24h
        })

    return {
        'posts': velocity_data,
        'has_data': len(velocity_data) > 0,
    }


def get_hashtag_performance(user, days=90):
    """
    Correlate hashtag groups with engagement metrics.

    Returns:
        Dictionary with per-group engagement averages
    """
    from postflow.models import ScheduledPost, TagGroup
    from analytics_pixelfed.models import PixelfedPost

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    # Get posts with hashtag groups that have been posted
    posts = ScheduledPost.objects.filter(
        user=user,
        status='posted',
        post_date__gte=start_date,
    ).prefetch_related('hashtag_groups__tags')

    group_stats = defaultdict(lambda: {'post_count': 0, 'total_engagement': 0, 'posts': []})

    for post in posts:
        # Try to find linked analytics post
        engagement = 0
        if post.pixelfed_post_id:
            try:
                pf_post = PixelfedPost.objects.select_related('engagement_summary').get(
                    pixelfed_post_id=post.pixelfed_post_id
                )
                if pf_post.engagement_summary:
                    engagement = pf_post.engagement_summary.total_engagement or 0
            except PixelfedPost.DoesNotExist:
                pass

        for group in post.hashtag_groups.all():
            group_stats[group.id]['post_count'] += 1
            group_stats[group.id]['total_engagement'] += engagement
            group_stats[group.id]['group_name'] = group.name
            group_stats[group.id]['tag_count'] = group.tags.count()

    results = []
    for gid, stats in group_stats.items():
        avg = stats['total_engagement'] / stats['post_count'] if stats['post_count'] > 0 else 0
        results.append({
            'group_id': gid,
            'group_name': stats['group_name'],
            'tag_count': stats['tag_count'],
            'post_count': stats['post_count'],
            'total_engagement': stats['total_engagement'],
            'avg_engagement': round(avg, 1),
        })

    results.sort(key=lambda x: x['avg_engagement'], reverse=True)

    return {
        'groups': results,
        'has_data': len(results) > 0,
    }


def get_top_performers(user, days=90, limit=10):
    """Top posts by engagement across all platforms."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    posts = []
    if accounts.exists():
        qs = PixelfedPost.objects.filter(
            account__in=accounts, posted_at__gte=start_date,
        ).select_related('engagement_summary', 'account').order_by(
            '-engagement_summary__total_engagement'
        )[:limit]
        for p in qs:
            eng = p.engagement_summary if hasattr(p, 'engagement_summary') and p.engagement_summary else None
            posts.append({
                'platform': 'pixelfed',
                'caption': (p.caption or '')[:80],
                'media_url': p.media_url,
                'post_url': p.post_url,
                'posted_at': p.posted_at,
                'total_engagement': eng.total_engagement if eng else 0,
                'likes': eng.total_likes if eng else 0,
                'comments': eng.total_comments if eng else 0,
                'shares': eng.total_shares if eng else 0,
            })

    posts.sort(key=lambda x: x['total_engagement'], reverse=True)
    return {'posts': posts[:limit], 'has_data': len(posts) > 0}


def get_consistency_score(user, days=90):
    """Calculate posting consistency score (0-100) and streak."""
    from analytics_pixelfed.models import PixelfedPost
    from analytics_mastodon.models import MastodonPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    posting_days = set()

    pf_accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if pf_accounts.exists():
        dates = PixelfedPost.objects.filter(
            account__in=pf_accounts, posted_at__gte=start_date,
        ).values_list('posted_at', flat=True)
        for d in dates:
            posting_days.add(d.date())

    m_accounts = MastodonNativeAccount.objects.filter(user=user)
    if m_accounts.exists():
        dates = MastodonPost.objects.filter(
            account__in=m_accounts, posted_at__gte=start_date,
        ).values_list('posted_at', flat=True)
        for d in dates:
            posting_days.add(d.date())

    total_days = days
    days_posted = len(posting_days)
    frequency = days_posted / total_days if total_days > 0 else 0

    # Score: 100 if posting every day, scaled down
    # Adjusted: posting 3x/week (43%) = score 70
    score = min(100, int(frequency * 230))

    # Calculate current streak
    current_streak = 0
    for i in range(days):
        check = (end_date - timedelta(days=i)).date()
        if check in posting_days:
            current_streak += 1
        else:
            break

    # Weekly breakdown
    weeks = defaultdict(int)
    for d in posting_days:
        week_num = d.isocalendar()[1]
        weeks[week_num] += 1

    avg_per_week = sum(weeks.values()) / max(len(weeks), 1)

    return {
        'score': score,
        'days_posted': days_posted,
        'total_days': total_days,
        'frequency_pct': round(frequency * 100, 1),
        'current_streak': current_streak,
        'avg_per_week': round(avg_per_week, 1),
        'has_data': days_posted > 0,
    }


def get_engagement_quality(user, days=90):
    """Weighted engagement quality: comments 3x > shares 2x > likes 1x."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'posts': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary').order_by('-posted_at')[:30]

    result = []
    for p in posts:
        eng = p.engagement_summary if hasattr(p, 'engagement_summary') and p.engagement_summary else None
        if not eng:
            continue
        likes = eng.total_likes or 0
        comments = eng.total_comments or 0
        shares = eng.total_shares or 0
        quality_score = likes + (comments * 3) + (shares * 2)
        quantity = likes + comments + shares
        result.append({
            'caption': (p.caption or '')[:60],
            'post_url': p.post_url,
            'posted_at': p.posted_at,
            'likes': likes,
            'comments': comments,
            'shares': shares,
            'quality_score': quality_score,
            'quantity': quantity,
            'ratio': round(quality_score / max(quantity, 1), 2),
        })

    result.sort(key=lambda x: x['quality_score'], reverse=True)
    return {'posts': result, 'has_data': len(result) > 0}


def get_growth_momentum(user, days=90):
    """Week-over-week engagement growth and velocity."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'weeks': [], 'max_engagement': 1, 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary').order_by('posted_at')

    weekly = defaultdict(lambda: {'engagement': 0, 'posts': 0})
    for p in posts:
        week_start = p.posted_at.date() - timedelta(days=p.posted_at.weekday())
        eng = p.engagement_summary.total_engagement if hasattr(p, 'engagement_summary') and p.engagement_summary else 0
        weekly[week_start]['engagement'] += eng
        weekly[week_start]['posts'] += 1

    weeks_sorted = sorted(weekly.items())
    result = []
    for i, (week, data) in enumerate(weeks_sorted):
        prev_eng = weeks_sorted[i-1][1]['engagement'] if i > 0 else 0
        growth = ((data['engagement'] - prev_eng) / max(prev_eng, 1)) * 100 if i > 0 else 0
        result.append({
            'week': week.isoformat(),
            'week_label': week.strftime('%b %d'),
            'engagement': data['engagement'],
            'posts': data['posts'],
            'growth_pct': round(growth, 1),
            'accelerating': growth > 0,
        })

    max_eng = max((w['engagement'] for w in result), default=1) or 1
    return {'weeks': result, 'max_engagement': max_eng, 'has_data': len(result) > 0}


def get_engagement_timeline(user, days=90, aggregation='daily'):
    """Enhanced engagement timeline with daily/weekly/monthly aggregation."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'data': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary').order_by('posted_at')

    buckets = defaultdict(lambda: {'likes': 0, 'comments': 0, 'shares': 0, 'posts': 0})

    for p in posts:
        eng = p.engagement_summary if hasattr(p, 'engagement_summary') and p.engagement_summary else None
        dt = p.posted_at.date()

        if aggregation == 'weekly':
            key = (dt - timedelta(days=dt.weekday())).isoformat()
        elif aggregation == 'monthly':
            key = dt.replace(day=1).isoformat()
        else:
            key = dt.isoformat()

        buckets[key]['posts'] += 1
        if eng:
            buckets[key]['likes'] += eng.total_likes or 0
            buckets[key]['comments'] += eng.total_comments or 0
            buckets[key]['shares'] += eng.total_shares or 0

    data = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        data.append({
            'date': key,
            'likes': b['likes'],
            'comments': b['comments'],
            'shares': b['shares'],
            'total': b['likes'] + b['comments'] + b['shares'],
            'posts': b['posts'],
        })

    # CSV data
    csv_lines = ['date,likes,comments,shares,total,posts']
    for d in data:
        csv_lines.append(f"{d['date']},{d['likes']},{d['comments']},{d['shares']},{d['total']},{d['posts']}")

    max_total = max((d['total'] for d in data), default=1) or 1

    return {'data': data, 'csv': '\n'.join(csv_lines), 'max_total': max_total, 'has_data': len(data) > 0}


def get_engagement_decay(user, days=90, limit=10):
    """Engagement over time after posting - identify long-tail content."""
    from analytics_pixelfed.models import PixelfedPost, PixelfedLike
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'posts': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary').filter(
        engagement_summary__total_engagement__gt=0
    ).order_by('-engagement_summary__total_engagement')[:limit]

    result = []
    for p in posts:
        total = p.engagement_summary.total_engagement
        # Count likes by time buckets
        day1 = p.likes.filter(first_seen_at__lte=p.posted_at + timedelta(hours=24)).count()
        day3 = p.likes.filter(first_seen_at__lte=p.posted_at + timedelta(days=3)).count()
        day7 = p.likes.filter(first_seen_at__lte=p.posted_at + timedelta(days=7)).count()
        day30 = p.likes.filter(first_seen_at__lte=p.posted_at + timedelta(days=30)).count()

        result.append({
            'caption': (p.caption or '')[:60],
            'post_url': p.post_url,
            'posted_at': p.posted_at,
            'total': total,
            'day1': day1,
            'day3': day3,
            'day7': day7,
            'day30': day30,
            'pct_day1': round(day1 / max(total, 1) * 100),
            'pct_day7': round(day7 / max(total, 1) * 100),
            'is_long_tail': day7 < total * 0.7,  # <70% in first week = long tail
        })

    return {'posts': result, 'has_data': len(result) > 0}


def get_caption_length_analysis(user, days=90):
    """Caption length vs engagement correlation."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'posts': [], 'has_data': False, 'sweet_spot': None}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary')

    data = []
    length_buckets = defaultdict(lambda: {'count': 0, 'total_eng': 0})

    for p in posts:
        eng = p.engagement_summary.total_engagement if hasattr(p, 'engagement_summary') and p.engagement_summary else 0
        caption_len = len(p.caption or '')
        data.append({'length': caption_len, 'engagement': eng, 'caption': (p.caption or '')[:40]})

        # Bucket by 50-char ranges
        bucket = (caption_len // 50) * 50
        length_buckets[bucket]['count'] += 1
        length_buckets[bucket]['total_eng'] += eng

    # Find sweet spot (bucket with highest avg engagement, min 3 posts)
    sweet_spot = None
    best_avg = 0
    buckets_list = []
    for bucket, stats in sorted(length_buckets.items()):
        avg = stats['total_eng'] / stats['count'] if stats['count'] > 0 else 0
        buckets_list.append({
            'range': f"{bucket}-{bucket + 49}",
            'count': stats['count'],
            'avg_engagement': round(avg, 1),
        })
        if stats['count'] >= 3 and avg > best_avg:
            best_avg = avg
            sweet_spot = f"{bucket}-{bucket + 49} chars"

    return {'posts': data, 'buckets': buckets_list, 'sweet_spot': sweet_spot, 'has_data': len(data) > 0}


def get_viral_coefficient(user, days=90):
    """Shares-to-likes ratio as virality indicator."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'posts': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary').filter(
        engagement_summary__total_likes__gt=0
    ).order_by('-posted_at')[:30]

    result = []
    for p in posts:
        eng = p.engagement_summary
        likes = eng.total_likes or 0
        shares = eng.total_shares or 0
        ratio = round(shares / max(likes, 1), 3)
        result.append({
            'caption': (p.caption or '')[:60],
            'post_url': p.post_url,
            'posted_at': p.posted_at,
            'likes': likes,
            'shares': shares,
            'ratio': ratio,
            'is_viral': ratio > 0.1,
        })

    result.sort(key=lambda x: x['ratio'], reverse=True)
    return {'posts': result, 'has_data': len(result) > 0}


def get_content_themes(user, days=90, limit=20):
    """Hashtag/keyword frequency analysis in high-engagement posts."""
    from analytics_pixelfed.models import PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount
    import re

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'tags': [], 'has_data': False}

    posts = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).select_related('engagement_summary')

    tag_stats = defaultdict(lambda: {'count': 0, 'total_eng': 0})

    for p in posts:
        eng = p.engagement_summary.total_engagement if hasattr(p, 'engagement_summary') and p.engagement_summary else 0
        # Extract hashtags from caption
        hashtags = re.findall(r'#(\w+)', p.caption or '')
        for tag in hashtags:
            tag_lower = tag.lower()
            tag_stats[tag_lower]['count'] += 1
            tag_stats[tag_lower]['total_eng'] += eng

    tags = []
    for tag, stats in tag_stats.items():
        avg = stats['total_eng'] / stats['count'] if stats['count'] > 0 else 0
        tags.append({
            'tag': tag,
            'count': stats['count'],
            'total_engagement': stats['total_eng'],
            'avg_engagement': round(avg, 1),
        })

    tags.sort(key=lambda x: x['avg_engagement'], reverse=True)
    max_count = max((t['count'] for t in tags), default=1) or 1

    return {'tags': tags[:limit], 'max_count': max_count, 'has_data': len(tags) > 0}


def get_conversation_threads(user, days=30, limit=20):
    """Thread view of comment chains for community conversation map."""
    from analytics_pixelfed.models import PixelfedComment, PixelfedPost
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount

    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    accounts = PixelfedMastodonAccount.objects.filter(user=user, instance_url__icontains='pixelfed')
    if not accounts.exists():
        return {'threads': [], 'has_data': False}

    # Get posts with multiple comments (conversations)
    from django.db.models import Count
    posts_with_threads = PixelfedPost.objects.filter(
        account__in=accounts, posted_at__gte=start_date,
    ).annotate(
        comment_count=Count('comments')
    ).filter(comment_count__gte=2).order_by('-comment_count')[:limit]

    threads = []
    for post in posts_with_threads:
        comments = list(post.comments.order_by('commented_at')[:20])
        threads.append({
            'post_caption': (post.caption or '')[:60],
            'post_url': post.post_url,
            'posted_at': post.posted_at,
            'comment_count': len(comments),
            'comments': [{
                'username': c.username,
                'content': c.content[:200],
                'commented_at': c.commented_at,
                'is_reply': c.is_reply,
            } for c in comments],
            'unique_participants': len(set(c.username for c in comments)),
        })

    return {'threads': threads, 'has_data': len(threads) > 0}


def get_posting_calendar_data(user, platform=None, days=365):
    """
    Aggregate posting calendar data across platforms or for a specific platform.

    Similar to GitHub's contribution graph, this generates a year-long calendar
    showing posting activity with engagement metrics.

    Args:
        user: Django User object
        platform: Optional platform filter ('pixelfed', 'mastodon', 'instagram'), None for all
        days: Number of days to look back (default: 365)

    Returns:
        Dictionary with calendar data, summary statistics, and intensity levels
    """
    from analytics_pixelfed.models import PixelfedPost, PixelfedEngagementSummary
    from analytics_mastodon.models import MastodonPost, MastodonEngagementSummary
    from analytics_instagram.models import InstagramPost, InstagramEngagementSummary
    from pixelfed.models import MastodonAccount as PixelfedMastodonAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount
    from instagram.models import InstagramBusinessAccount

    # Calculate date range (last 365 days by default)
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    # Dictionary to store daily aggregates
    # Key: date string 'YYYY-MM-DD', Value: post data
    daily_data = defaultdict(lambda: {
        'date': None,
        'post_count': 0,
        'total_engagement': 0,
        'posts': []
    })

    # Helper function to add post to daily data
    def add_post_to_calendar(post, platform_name, engagement):
        """Add a post to the calendar data structure"""
        post_date = post.posted_at.date()
        date_key = post_date.isoformat()

        # Initialize date if first post
        if daily_data[date_key]['date'] is None:
            daily_data[date_key]['date'] = date_key

        # Increment counts
        daily_data[date_key]['post_count'] += 1
        daily_data[date_key]['total_engagement'] += engagement

        # Add post details (limit preview length)
        content_preview = ''
        if hasattr(post, 'caption'):
            content_preview = post.caption[:100] if post.caption else ''
        elif hasattr(post, 'content'):
            content_preview = post.content[:100] if post.content else ''

        daily_data[date_key]['posts'].append({
            'id': post.id,
            'platform': platform_name.lower(),
            'platform_name': platform_name,
            'content_preview': content_preview,
            'engagement': engagement,
            'url': post.post_url if hasattr(post, 'post_url') else '',
        })

    # Fetch Pixelfed posts
    if platform is None or platform == 'pixelfed':
        pixelfed_accounts = PixelfedMastodonAccount.objects.filter(
            user=user,
            instance_url__icontains='pixelfed'
        )

        if pixelfed_accounts.exists():
            pixelfed_posts = PixelfedPost.objects.filter(
                account__in=pixelfed_accounts,
                posted_at__gte=start_date,
                posted_at__lte=end_date
            ).select_related('engagement_summary').order_by('posted_at')

            for post in pixelfed_posts:
                engagement = 0
                if hasattr(post, 'engagement_summary') and post.engagement_summary:
                    engagement = post.engagement_summary.total_engagement or 0
                add_post_to_calendar(post, 'Pixelfed', engagement)

    # Fetch Mastodon posts
    if platform is None or platform == 'mastodon':
        mastodon_accounts = MastodonNativeAccount.objects.filter(user=user)

        if mastodon_accounts.exists():
            mastodon_posts = MastodonPost.objects.filter(
                account__in=mastodon_accounts,
                posted_at__gte=start_date,
                posted_at__lte=end_date
            ).select_related('engagement_summary').order_by('posted_at')

            for post in mastodon_posts:
                engagement = 0
                if hasattr(post, 'engagement_summary') and post.engagement_summary:
                    engagement = post.engagement_summary.total_engagement or 0
                add_post_to_calendar(post, 'Mastodon', engagement)

    # Fetch Instagram posts
    if platform is None or platform == 'instagram':
        instagram_accounts = InstagramBusinessAccount.objects.filter(user=user)

        if instagram_accounts.exists():
            instagram_posts = InstagramPost.objects.filter(
                account__in=instagram_accounts,
                posted_at__gte=start_date,
                posted_at__lte=end_date
            ).select_related('engagement_summary').order_by('posted_at')

            for post in instagram_posts:
                engagement = 0
                if hasattr(post, 'engagement_summary') and post.engagement_summary:
                    engagement = post.engagement_summary.total_engagement or 0
                add_post_to_calendar(post, 'Instagram', engagement)

    # Convert defaultdict to sorted list
    calendar_data = sorted(daily_data.values(), key=lambda x: x['date'] or '')

    # Calculate summary statistics
    total_posts = sum(day['post_count'] for day in calendar_data)
    days_with_posts = sum(1 for day in calendar_data if day['post_count'] > 0)

    # Calculate streaks
    current_streak = 0
    longest_streak = 0
    temp_streak = 0

    # Create full date range for streak calculation
    current_date = end_date.date()
    date_has_posts = {day['date']: day['post_count'] > 0 for day in calendar_data}

    # Calculate current streak (from today backwards)
    for i in range(days):
        check_date = (end_date - timedelta(days=i)).date()
        date_key = check_date.isoformat()

        if date_has_posts.get(date_key, False):
            current_streak += 1
        else:
            break  # Streak broken

    # Calculate longest streak
    for i in range(days):
        check_date = (start_date + timedelta(days=i)).date()
        date_key = check_date.isoformat()

        if date_has_posts.get(date_key, False):
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
        else:
            temp_streak = 0

    # Find busiest day
    busiest_day = None
    max_posts = 0
    for day in calendar_data:
        if day['post_count'] > max_posts:
            max_posts = day['post_count']
            busiest_day = {'date': day['date'], 'post_count': day['post_count']}

    # Calculate average posts per day
    avg_posts_per_day = round(total_posts / days, 2) if days > 0 else 0

    # Calculate intensity levels (for color coding)
    # Based on post count distribution
    post_counts = [day['post_count'] for day in calendar_data if day['post_count'] > 0]

    if post_counts:
        # Simple thresholds
        intensity_levels = {
            'level_0': 0,  # No posts
            'level_1': 1,  # 1 post
            'level_2': 2,  # 2 posts
            'level_3': 3,  # 3-4 posts
            'level_4': 5,  # 5+ posts
        }
    else:
        intensity_levels = {
            'level_0': 0,
            'level_1': 1,
            'level_2': 2,
            'level_3': 3,
            'level_4': 5,
        }

    # Generate calendar grid structure (weeks and days)
    # Start from the first Sunday before start_date to align grid properly
    calendar_start = start_date.date()
    while calendar_start.weekday() != 6:  # 6 = Sunday
        calendar_start = calendar_start - timedelta(days=1)

    # Create grid: list of weeks, each containing 7 days
    calendar_grid = []
    current_date = calendar_start
    week_row = []
    month_labels = []

    while current_date <= end_date.date():
        # Track month changes for labels
        if len(week_row) == 0 and current_date.day <= 7:
            month_labels.append({
                'week_index': len(calendar_grid),
                'month_name': current_date.strftime('%b')
            })

        # Get data for this date
        date_key = current_date.isoformat()
        day_info = None
        for day_data in calendar_data:
            if day_data.get('date') == date_key:
                day_info = day_data
                break

        # Determine intensity level
        post_count = day_info['post_count'] if day_info else 0
        if post_count == 0:
            intensity = 0
        elif post_count == 1:
            intensity = 1
        elif post_count == 2:
            intensity = 2
        elif post_count <= 4:
            intensity = 3
        else:
            intensity = 4

        # Add day to week
        week_row.append({
            'date': current_date,
            'date_str': date_key,
            'is_future': current_date > end_date.date(),
            'post_count': post_count,
            'total_engagement': day_info['total_engagement'] if day_info else 0,
            'posts': day_info['posts'] if day_info else [],
            'intensity': intensity,
            'formatted_date': current_date.strftime('%A, %B %d, %Y'),
        })

        # Complete week (7 days)
        if len(week_row) == 7:
            calendar_grid.append(week_row)
            week_row = []

        current_date = current_date + timedelta(days=1)

    # Add any remaining partial week
    if week_row:
        # Pad with empty cells if needed
        while len(week_row) < 7:
            week_row.append(None)
        calendar_grid.append(week_row)

    return {
        'calendar_data': calendar_data,
        'calendar_grid': calendar_grid,
        'month_labels': month_labels,
        'summary': {
            'total_days': days,
            'days_with_posts': days_with_posts,
            'total_posts': total_posts,
            'current_streak': current_streak,
            'longest_streak': longest_streak,
            'avg_posts_per_day': avg_posts_per_day,
            'busiest_day': busiest_day,
        },
        'intensity_levels': intensity_levels,
    }
