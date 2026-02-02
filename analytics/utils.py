"""
Utility functions for analytics apps.
"""


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
