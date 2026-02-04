"""
Template tags and filters for analytics apps.
"""
from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()


@register.filter
def get_metric(obj, metric_key):
    """
    Dynamically get metric value from engagement_summary.

    Usage: {{ post|get_metric:"likes" }}
    """
    if hasattr(obj, 'engagement_summary') and obj.engagement_summary:
        # Try the exact key first
        if hasattr(obj.engagement_summary, metric_key):
            return getattr(obj.engagement_summary, metric_key, 0)
        # Try with total_ prefix
        total_key = f'total_{metric_key}'
        if hasattr(obj.engagement_summary, total_key):
            return getattr(obj.engagement_summary, total_key, 0)
    return 0


@register.filter
def get_content_field(post, platform_slug):
    """
    Get the appropriate content field for the platform.

    Usage: {{ post|get_content_field:platform.slug }}
    """
    if platform_slug == 'pixelfed':
        return post.caption_text if hasattr(post, 'caption_text') else ''
    elif platform_slug == 'mastodon':
        return post.content_text if hasattr(post, 'content_text') else ''
    elif platform_slug == 'instagram':
        return post.caption_text if hasattr(post, 'caption_text') else ''
    return ''


@register.filter
def get_username_field(post, platform_slug):
    """
    Get the username for display.

    Usage: {{ post|get_username_field:platform.slug }}
    """
    if hasattr(post, 'username'):
        return post.username
    elif hasattr(post, 'account') and hasattr(post.account, 'username'):
        return post.account.username
    return 'Unknown'


@register.simple_tag
def build_url(url_namespace, view_name, *args):
    """
    Build URL with namespace dynamically.

    Usage: {% build_url platform.url_namespace 'dashboard' %}
    """
    from django.urls import reverse
    full_name = f"{url_namespace}:{view_name}"
    if args:
        return reverse(full_name, args=args)
    return reverse(full_name)


@register.filter
def time_ago(timestamp):
    """
    Format a timestamp as relative time ago (e.g., "5 mins ago", "2 hours ago").

    Usage: {{ account.last_posts_sync_at|time_ago }}
    """
    if not timestamp:
        return "Never"

    now = timezone.now()
    diff = now - timestamp

    if diff < timedelta(minutes=1):
        return "Just now"
    elif diff < timedelta(hours=1):
        mins = int(diff.total_seconds() / 60)
        return f"{mins} min{'s' if mins != 1 else ''} ago"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff < timedelta(days=7):
        days = int(diff.total_seconds() / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return timestamp.strftime("%b %d, %Y")


@register.filter
def time_until(timestamp):
    """
    Format a future timestamp as time until (e.g., "in 5 mins", "in 2 hours").

    Usage: {{ account.next_posts_sync_at|time_until }}
    """
    if not timestamp:
        return "Not scheduled"

    now = timezone.now()
    if timestamp <= now:
        return "Soon"

    diff = timestamp - now

    if diff < timedelta(minutes=1):
        return "In less than a minute"
    elif diff < timedelta(hours=1):
        mins = int(diff.total_seconds() / 60)
        return f"In {mins} min{'s' if mins != 1 else ''}"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"In {hours} hour{'s' if hours != 1 else ''}"
    else:
        days = int(diff.total_seconds() / 86400)
        return f"In {days} day{'s' if days != 1 else ''}"
