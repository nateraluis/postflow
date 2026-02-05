"""
Template tags for Plausible analytics tracking.

Usage in templates:
    {% load plausible_tags %}

    <a href="{% url 'register' %}" {% plausible_event "Signup Click" source="hero" %}>
        Get Started
    </a>
"""
from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()


@register.simple_tag
def plausible_event(event_name, **props):
    """
    Generate onclick attribute for Plausible event tracking.

    Usage:
        {% plausible_event "Signup Click" source="hero" %}
        {% plausible_event "Checkout Start" plan="monthly" %}
    """
    if props:
        props_json = json.dumps(props)
        onclick = f"plausible('{event_name}', {{props: {props_json}}})"
    else:
        onclick = f"plausible('{event_name}')"

    return mark_safe(f'onclick="{onclick}"')


@register.simple_tag
def plausible_revenue_event(event_name, amount, currency='USD', **props):
    """
    Generate onclick attribute for Plausible revenue tracking.

    Usage:
        {% plausible_revenue_event "Subscription" 1000 "USD" plan="monthly" %}
    """
    revenue = {'amount': amount, 'currency': currency}
    if props:
        props_json = json.dumps(props)
        onclick = f"plausible('{event_name}', {{revenue: {json.dumps(revenue)}, props: {props_json}}})"
    else:
        onclick = f"plausible('{event_name}', {{revenue: {json.dumps(revenue)}}})"

    return mark_safe(f'onclick="{onclick}"')


@register.simple_tag
def plausible_track_pageview(props=None):
    """
    Generate inline script to track page view with custom properties.

    Usage:
        {% plausible_track_pageview %}
        {% plausible_track_pageview '{"source": "preview"}' %}
    """
    if props:
        return mark_safe(f'<script>plausible("pageview", {{props: {props}}});</script>')
    return ''
