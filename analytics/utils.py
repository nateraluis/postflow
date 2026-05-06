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
