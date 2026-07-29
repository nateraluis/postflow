"""Series and attribution helpers for the site analytics dashboard."""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from campaigns.utm import PLATFORM_UTM_SOURCES
from postflow.models import ScheduledPost

from .models import SiteSnapshot

# Order matters: first non-empty M2M wins. Maps the account relation to the
# canonical platform/utm_source key used across the app.
_POST_PLATFORM_FIELDS = [
    ("instagram_accounts", "instagram"),
    ("mastodon_accounts", "pixelfed"),
    ("mastodon_native_accounts", "mastodon"),
    ("linkedin_accounts", "linkedin"),
    ("threads_accounts", "threads"),
    ("glass_accounts", "glass"),
]


def _dim(row: dict, default="?") -> str:
    dims = row.get("dimensions") or row.get("keys") or []
    return dims[0] if dims else default


def _metric(row: dict, index: int = 0):
    metrics = row.get("metrics")
    if metrics and index < len(metrics):
        return metrics[index]
    return 0


def get_series(website, days=30):
    """Ascending list of {date, visitors, pageviews, subscribers, subscriber_delta}."""
    if website is None:
        return []
    start = timezone.now().date() - timedelta(days=days)
    snapshots = SiteSnapshot.objects.filter(website=website, date__gte=start).order_by("date")
    return [
        {
            "date": s.date,
            "visitors": s.visitors,
            "pageviews": s.pageviews,
            "subscribers": s.subscribers,
            "subscriber_delta": s.subscriber_delta,
        }
        for s in snapshots
    ]


def get_signups_by_source(website, days=30):
    """Aggregate Plausible signups-by-source across snapshots in the window.

    Returns [{"source": ..., "count": ...}, ...] sorted descending, or [] if
    no snapshot has signups-by-source data.
    """
    if website is None:
        return []
    start = timezone.now().date() - timedelta(days=days)
    snapshots = SiteSnapshot.objects.filter(website=website, date__gte=start)

    totals = defaultdict(int)
    for snapshot in snapshots:
        for row in (snapshot.plausible or {}).get("signups_by_source") or []:
            totals[_dim(row)] += _metric(row)

    return [
        {"source": source, "count": count}
        for source, count in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def get_utm_sources(website, days=30):
    """Aggregate Plausible's source breakdown across snapshots, tagging
    entries that match a campaign platform's utm_source as campaign-driven.
    """
    if website is None:
        return []
    start = timezone.now().date() - timedelta(days=days)
    snapshots = SiteSnapshot.objects.filter(website=website, date__gte=start)

    campaign_sources = {value.lower() for value in PLATFORM_UTM_SOURCES.values()}
    totals = defaultdict(int)
    for snapshot in snapshots:
        for row in (snapshot.plausible or {}).get("sources") or []:
            totals[_dim(row)] += _metric(row)

    return [
        {
            "source": source,
            "visitors": visitors,
            "is_campaign": source.lower() in campaign_sources,
        }
        for source, visitors in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def _post_platform(post):
    for field, platform in _POST_PLATFORM_FIELDS:
        if getattr(post, field).exists():
            return platform
    return None


def get_post_impact(user, website, days=30):
    """For each posted ScheduledPost in range, compare visitors on the post
    day + the following day against the average of the 3 days before.

    Returns [{post, platform, post_date, visitors_after, baseline, lift_pct}].
    Missing snapshots are handled gracefully: entries with no data at all on
    either side of the comparison are skipped rather than raising.
    """
    if website is None:
        return []
    since = timezone.now() - timedelta(days=days)
    posts = (
        ScheduledPost.objects.filter(user=user, status="posted", post_date__gte=since)
        .order_by("-post_date")
        .prefetch_related(
            "instagram_accounts", "mastodon_accounts", "mastodon_native_accounts",
            "linkedin_accounts", "threads_accounts", "glass_accounts",
        )
    )

    snapshots_by_date = {
        s.date: s.visitors
        for s in SiteSnapshot.objects.filter(website=website).only("date", "visitors")
    }

    results = []
    for post in posts:
        post_date = timezone.localtime(post.post_date).date()

        after_values = [
            snapshots_by_date.get(post_date + timedelta(days=offset))
            for offset in (0, 1)
        ]
        after_values = [v for v in after_values if v is not None]

        before_values = [
            snapshots_by_date.get(post_date - timedelta(days=offset))
            for offset in (1, 2, 3)
        ]
        before_values = [v for v in before_values if v is not None]

        if not after_values and not before_values:
            continue

        visitors_after = sum(after_values) if after_values else None
        baseline = sum(before_values) / len(before_values) if before_values else None

        lift_pct = None
        if visitors_after is not None and baseline:
            expected = baseline * len(after_values)
            if expected:
                lift_pct = round((visitors_after - expected) / expected * 100, 1)

        results.append({
            "post": post,
            "platform": _post_platform(post),
            "post_date": post_date,
            "visitors_after": visitors_after,
            "baseline": round(baseline, 1) if baseline is not None else None,
            "lift_pct": lift_pct,
        })

    return results
