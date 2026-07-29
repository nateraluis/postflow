"""Google Search Console provider.

google-auth isn't a project dependency, so the OAuth token refresh is done
by hand with plain `requests` instead of the google-auth-* libraries used by
photo-analytics/site-report.py. The query shape (totals + queries + pages)
mirrors site-report.py so the blob looks like photo-analytics' stored JSON:

{
    "totals": {"clicks": ..., "impressions": ..., "ctr": ..., "position": ...},
    "queries": [{"keys": [query], "clicks": ..., "impressions": ..., "ctr": ..., "position": ...}, ...],
    "pages": [{"keys": [page], "clicks": ..., "impressions": ..., "ctr": ..., "position": ...}, ...],
}

Note: GSC data lags 2-3 days behind real time. We still query for the
requested date (with dataState="all" to include fresh/partial data) and
simply return whatever Google gives us — callers should expect recent days
to be sparse or empty until they settle.
"""
from urllib.parse import urlparse, quote

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEARCH_ANALYTICS_URL = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
TIMEOUT = 30


def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ValueError("GSC token refresh did not return an access_token")
    return token


def _default_site_url(website) -> str:
    host = urlparse(website.url).netloc or website.url
    return f"sc-domain:{host}"


def _query(access_token: str, site_url: str, body: dict) -> dict:
    resp = requests.post(
        SEARCH_ANALYTICS_URL.format(site=quote(site_url, safe="")),
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=body,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def collect(connection, date) -> dict:
    """Collect a single day of GSC search analytics for `connection`.

    Raises requests.RequestException (or ValueError for missing config) on failure.
    """
    client_id = connection.config.get("client_id")
    client_secret = connection.config.get("client_secret")
    refresh_token = connection.config.get("refresh_token")
    if not client_id or not client_secret or not refresh_token:
        raise ValueError("GSC connection is missing client_id/client_secret/refresh_token")

    site_url = connection.config.get("site_url") or _default_site_url(connection.website)

    access_token = _refresh_access_token(client_id, client_secret, refresh_token)

    day = date.isoformat()
    data: dict = {}

    r = _query(access_token, site_url, {"startDate": day, "endDate": day, "dataState": "all"})
    rows = r.get("rows") or []
    data["totals"] = rows[0] if rows else {}

    r = _query(access_token, site_url, {
        "startDate": day, "endDate": day,
        "dimensions": ["query"], "rowLimit": 20, "dataState": "all",
    })
    data["queries"] = r.get("rows", [])

    r = _query(access_token, site_url, {
        "startDate": day, "endDate": day,
        "dimensions": ["page"], "rowLimit": 20, "dataState": "all",
    })
    data["pages"] = r.get("rows", [])

    return data
