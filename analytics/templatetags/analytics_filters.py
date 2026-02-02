"""
Template tags and filters for analytics apps.
"""
from django import template

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
