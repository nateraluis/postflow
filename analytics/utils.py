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
