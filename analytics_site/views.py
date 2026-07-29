from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from websites.models import Website

from .models import AnalyticsConnection
from .utils import (
    get_post_impact,
    get_seo_overview,
    get_series,
    get_signups_by_source,
    get_utm_sources,
)

PROVIDER_CONFIG_FIELDS = {
    "plausible": ["api_key", "site_id"],
    "gsc": ["client_id", "client_secret", "refresh_token", "site_url"],
    "ghost_admin": ["admin_api_key"],
}


def _dashboard_url(website_id=None):
    url = reverse("analytics_site:dashboard")
    if website_id:
        url += f"?website={website_id}"
    return url


@login_required
def dashboard(request):
    websites = request.user.websites.all().order_by("created_at")

    website_id = request.GET.get("website")
    if website_id and website_id.isdigit():
        website = get_object_or_404(Website, pk=website_id, user=request.user)
    else:
        website = websites.first()

    context = {
        "websites": websites,
        "website": website,
        "active_page": "analytics",
        "provider_choices": AnalyticsConnection.PROVIDER_CHOICES,
    }

    if website is not None:
        series = get_series(website, days=30)
        connections = list(website.analytics_connections.all())
        connected_providers = {c.provider for c in connections}

        subscriber_delta_range = None
        dated_series = [row for row in series if row["subscribers"] is not None]
        if len(dated_series) >= 2:
            subscriber_delta_range = dated_series[-1]["subscribers"] - dated_series[0]["subscribers"]

        max_visitors = max((row["visitors"] or 0 for row in series), default=0)

        context.update({
            "series": series,
            "max_visitors": max_visitors,
            "signups_by_source": get_signups_by_source(website, days=30),
            "utm_sources": get_utm_sources(website, days=30),
            "post_impact": get_post_impact(request.user, website, days=30),
            "seo": get_seo_overview(website, days=28),
            "connections": connections,
            "available_providers": [
                (value, label) for value, label in AnalyticsConnection.PROVIDER_CHOICES
                if value not in connected_providers
            ],
            "totals": series[-1] if series else None,
            "subscriber_delta_range": subscriber_delta_range,
        })

    return render(request, "analytics_site/dashboard.html", context)


@login_required
@require_POST
def add_connection(request, website_id):
    website = get_object_or_404(Website, pk=website_id, user=request.user)

    provider = request.POST.get("provider")
    fields = PROVIDER_CONFIG_FIELDS.get(provider)
    if fields is None:
        messages.error(request, "Unknown analytics provider.")
        return redirect(_dashboard_url(website.id))

    config = {}
    for field in fields:
        value = request.POST.get(field, "").strip()
        if value:
            config[field] = value

    required_fields = fields if provider != "gsc" else ["client_id", "client_secret", "refresh_token"]
    if not all(config.get(field) for field in required_fields):
        messages.error(request, "Missing required fields for that connection.")
        return redirect(_dashboard_url(website.id))

    AnalyticsConnection.objects.update_or_create(
        website=website, provider=provider,
        defaults={"config": config, "is_active": True},
    )
    messages.success(request, "Connection added.")
    return redirect(_dashboard_url(website.id))


@login_required
@require_POST
def delete_connection(request, pk):
    connection = get_object_or_404(AnalyticsConnection, pk=pk, website__user=request.user)
    website_id = connection.website_id
    connection.delete()
    messages.success(request, "Connection removed.")
    return redirect(_dashboard_url(website_id))
