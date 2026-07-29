"""Ghost Admin API provider — pulls total member count for growth tracking.

Blob shape mirrors the path photo-analytics stores at `ghost.growth.summary`
(see photo-analytics/CLAUDE.md) so collect.py / the historical importer can
treat live-collected and imported snapshots identically:

{
    "growth": {"summary": {"total_members": N}},
    "collected_at": "2026-07-29T00:00:00+00:00",
}

pyjwt isn't a project dependency, so the Ghost Admin JWT (HS256, 5 minute
expiry) is built by hand from stdlib hmac/hashlib/base64 — it's a handful of
lines and avoids adding a dependency for one token.
"""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests

TIMEOUT = 30
TOKEN_TTL_SECONDS = 5 * 60


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _build_admin_jwt(admin_api_key: str) -> str:
    key_id, _, secret_hex = admin_api_key.partition(":")
    if not key_id or not secret_hex:
        raise ValueError("Ghost admin_api_key must be in 'id:secret' format")
    secret = bytes.fromhex(secret_hex)

    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": now, "exp": now + TOKEN_TTL_SECONDS, "aud": "/admin/"}

    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header_b64 + b"." + payload_b64

    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url(signature)

    return (signing_input + b"." + signature_b64).decode()


def collect(connection, date) -> dict:
    """Collect the current total member count for `connection`.

    Ghost's members list doesn't support historical/point-in-time queries,
    so this always reflects the count *as of now* regardless of `date` —
    callers should treat it as the latest known value for that day.
    Raises requests.RequestException (or ValueError for missing config) on failure.
    """
    admin_api_key = connection.config.get("admin_api_key")
    if not admin_api_key:
        raise ValueError("Ghost admin connection is missing admin_api_key")

    token = _build_admin_jwt(admin_api_key)
    base_url = connection.website.url.rstrip("/") + "/"
    url = urljoin(base_url, "ghost/api/admin/members/?limit=1")

    # The URL is user-controlled; block loopback/private/link-local targets
    from websites.sources.base import validate_public_url

    validate_public_url(url)

    resp = requests.get(
        url,
        headers={"Authorization": f"Ghost {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    total = payload.get("meta", {}).get("pagination", {}).get("total")

    return {
        "growth": {"summary": {"total_members": total}},
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
