"""Plausible Analytics provider.

Ports the query shape used by photo-analytics/site-report.py (Plausible v2
`/api/v2/query` endpoint) but scoped to a single day instead of a rolling
window, since collect.py calls this once per day.

Blob shape (mirrors photo-analytics' stored JSON so downstream code / the
historical import can treat both the same way):

{
    "aggregate": {"metrics": [visitors, pageviews, bounce_rate, visit_duration, visits]},
    "pages": [{"dimensions": [page], "metrics": [visitors, pageviews, bounce_rate, duration]}, ...],
    "sources": [{"dimensions": [source], "metrics": [visitors]}, ...],
    "signups_by_source": [{"dimensions": [source], "metrics": [count]}, ...],
}
"""
import requests

PLAUSIBLE_BASE = "https://plausible.io"
TIMEOUT = 30


def _query(api_key: str, site_id: str, body: dict) -> dict:
    resp = requests.post(
        f"{PLAUSIBLE_BASE}/api/v2/query",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"site_id": site_id, **body},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def collect(connection, date) -> dict:
    """Collect a single day of Plausible stats for `connection`.

    Raises requests.RequestException (or ValueError for missing config) on failure.
    """
    api_key = connection.config.get("api_key")
    site_id = connection.config.get("site_id")
    if not api_key or not site_id:
        raise ValueError("Plausible connection is missing api_key/site_id")

    day = date.isoformat()
    date_range = [day, day]
    data: dict = {}

    r = _query(api_key, site_id, {
        "metrics": ["visitors", "pageviews", "bounce_rate", "visit_duration", "visits"],
        "date_range": date_range,
    })
    results = r.get("results") or []
    data["aggregate"] = results[0] if results else {"metrics": []}

    r = _query(api_key, site_id, {
        "metrics": ["visitors", "pageviews", "bounce_rate", "visit_duration"],
        "date_range": date_range,
        "dimensions": ["event:page"],
        "order_by": [["visitors", "desc"]],
        "pagination": {"limit": 20},
    })
    data["pages"] = r.get("results", [])

    r = _query(api_key, site_id, {
        "metrics": ["visitors"],
        "date_range": date_range,
        "dimensions": ["visit:source"],
        "order_by": [["visitors", "desc"]],
        "pagination": {"limit": 20},
    })
    data["sources"] = r.get("results", [])

    # Signups-by-source goal breakdown — mirrors site-report.py's
    # "Signup"/"Signup-Confirmed" custom event filter. Optional: some sites
    # won't have this goal configured, so tolerate an empty/failed response.
    try:
        r = _query(api_key, site_id, {
            "metrics": ["visitors"],
            "date_range": date_range,
            "dimensions": ["visit:source"],
            "filters": [["is", "event:name", ["Signup", "Signup-Confirmed"]]],
            "order_by": [["visitors", "desc"]],
        })
        data["signups_by_source"] = r.get("results", [])
    except requests.RequestException:
        data["signups_by_source"] = []

    return data
