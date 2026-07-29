"""Orchestrates provider collection into SiteSnapshot rows.

One provider failing must never stop the others from being collected or
saved — each connection is collected independently and errors are recorded
on the connection itself (last_error) rather than raised.
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone

from .models import SiteSnapshot
from .providers import ghost_admin, gsc, plausible

logger = logging.getLogger("postflow")

# Maps AnalyticsConnection.provider -> (collector module, SiteSnapshot blob field)
PROVIDER_FUNCS = {
    "plausible": (plausible, "plausible"),
    "gsc": (gsc, "gsc"),
    "ghost_admin": (ghost_admin, "ghost"),
}


def _yesterday_utc():
    return (datetime.now(dt_timezone.utc) - timedelta(days=1)).date()


def collect_website(website, date=None):
    """Collect all active connections for `website` into a SiteSnapshot for `date`.

    `date` defaults to yesterday (UTC). Returns (snapshot, results) where
    results is {provider: "ok"} or {provider: "error: <message>"}.
    """
    if date is None:
        date = _yesterday_utc()

    snapshot, _ = SiteSnapshot.objects.get_or_create(website=website, date=date)
    results = {}

    for connection in website.analytics_connections.filter(is_active=True):
        entry = PROVIDER_FUNCS.get(connection.provider)
        if entry is None:
            continue
        module, field = entry
        try:
            blob = module.collect(connection, date)
            setattr(snapshot, field, blob)
            connection.last_error = ""
            results[connection.provider] = "ok"
        except Exception as exc:  # noqa: BLE001 - one provider's failure must not kill the rest
            logger.warning("analytics_site: %s collection failed for %s: %s", connection.provider, website, exc)
            connection.last_error = str(exc)
            results[connection.provider] = f"error: {exc}"
        connection.last_collected_at = timezone.now()
        connection.save(update_fields=["last_collected_at", "last_error"])

    _denormalise(snapshot, website)
    snapshot.save()
    return snapshot, results


def _denormalise(snapshot, website):
    """Populate visitors/pageviews/subscribers/subscriber_delta from raw blobs."""
    metrics = (snapshot.plausible or {}).get("aggregate", {}).get("metrics") or []
    if len(metrics) > 0:
        snapshot.visitors = metrics[0]
    if len(metrics) > 1:
        snapshot.pageviews = metrics[1]

    total_members = (snapshot.ghost or {}).get("growth", {}).get("summary", {}).get("total_members")
    if total_members is not None:
        snapshot.subscribers = total_members
        previous = (
            SiteSnapshot.objects.filter(website=website, date__lt=snapshot.date, subscribers__isnull=False)
            .order_by("-date")
            .first()
        )
        if previous is not None:
            snapshot.subscriber_delta = total_members - previous.subscribers
