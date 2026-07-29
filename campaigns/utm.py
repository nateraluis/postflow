"""UTM tagging for campaign links.

The utm_source values here are the canonical join keys for attribution:
analytics_site matches Plausible's recorded sources against this mapping.
"""
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

PLATFORM_UTM_SOURCES = {
    "instagram": "instagram",
    "pixelfed": "pixelfed",
    "mastodon": "mastodon",
    "linkedin": "linkedin",
    "threads": "threads",
    "glass": "glass",
}


def tag_url(url: str, platform: str, utm_campaign: str) -> str:
    """Append utm parameters to a URL, preserving existing query params."""
    source = PLATFORM_UTM_SOURCES.get(platform, platform)
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query))
    params.update({
        "utm_source": source,
        "utm_medium": "social",
        "utm_campaign": utm_campaign,
    })
    return urlunparse(parsed._replace(query=urlencode(params)))
