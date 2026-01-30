"""
Custom template filters for analytics templates.
"""
from django import template

register = template.Library()


@register.filter(name='getattr')
def getattribute(obj, attr_name):
    """
    Get attribute from object dynamically.

    Usage: {{ object|getattr:"attribute_name" }}
    """
    if obj is None:
        return None
    return getattr(obj, attr_name, None)
