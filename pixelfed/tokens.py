"""Access-token lifetime handling for Pixelfed/Mastodon-compatible accounts.

Pixelfed issues JWT access tokens that expire after a year and reports auth
failures as HTTP 500 {"error": "Unauthenticated."}, so an expired token looks
like a server error unless we track expiry ourselves and refresh proactively.
"""
import base64
import datetime
import json
import logging

import requests
from django.utils import timezone

logger = logging.getLogger("postflow")

# Refresh this far ahead of expiry so a scheduled post never hits a dead token.
REFRESH_WINDOW = datetime.timedelta(days=7)


def token_expiry_from_jwt(access_token):
    """Read the exp claim from a JWT access token; None if not a JWT."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        if exp:
            return datetime.datetime.fromtimestamp(exp, datetime.timezone.utc)
    except (IndexError, ValueError, TypeError):
        pass
    return None


def ensure_fresh_token(account):
    """Make sure the account's access token is usable; refresh it if needed.

    Returns True when the token is (believed) valid, False when it has expired
    and cannot be refreshed — in that case the account must be reconnected.
    """
    if not account.token_expires_at:
        expiry = token_expiry_from_jwt(account.access_token)
        if expiry is None:
            return True  # opaque token, no expiry info — assume valid
        account.token_expires_at = expiry
        account.save(update_fields=["token_expires_at"])

    now = timezone.now()
    if account.token_expires_at - now > REFRESH_WINDOW:
        return True

    if account.refresh_token and account.client_id and account.client_secret:
        if refresh_access_token(account):
            return True

    if account.token_expires_at <= now:
        logger.error(
            f"Pixelfed access token for @{account.username} on {account.instance_url} "
            f"expired at {account.token_expires_at:%Y-%m-%d %H:%M} UTC and cannot be "
            "refreshed. Reconnect the account from the Accounts page."
        )
        return False

    logger.warning(
        f"Pixelfed access token for @{account.username} expires at "
        f"{account.token_expires_at:%Y-%m-%d %H:%M} UTC and no refresh token is "
        "stored. Reconnect the account before then."
    )
    return True  # still valid for now


def refresh_access_token(account):
    """Exchange the stored refresh token for a new access token."""
    try:
        response = requests.post(
            f"{account.instance_url}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": account.refresh_token,
                "client_id": account.client_id,
                "client_secret": account.client_secret,
                "scope": "read write",
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()
    except requests.RequestException as e:
        body = e.response.text[:300] if getattr(e, "response", None) is not None else str(e)
        logger.error(f"Failed to refresh Pixelfed token for @{account.username}: {body}")
        return False

    account.access_token = token_data["access_token"]
    if token_data.get("refresh_token"):
        account.refresh_token = token_data["refresh_token"]
    if token_data.get("expires_in"):
        account.token_expires_at = timezone.now() + datetime.timedelta(seconds=token_data["expires_in"])
    else:
        account.token_expires_at = token_expiry_from_jwt(account.access_token)
    account.save(update_fields=["access_token", "refresh_token", "token_expires_at"])
    logger.info(
        f"Refreshed Pixelfed access token for @{account.username}, "
        f"new expiry {account.token_expires_at}"
    )
    return True
