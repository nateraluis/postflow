import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods

from .models import ThreadsAccount

logger = logging.getLogger("postflow")

THREADS_AUTHORIZE_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_EXCHANGE_URL = "https://graph.threads.net/access_token"
THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"
THREADS_GRAPH_BASE = "https://graph.threads.net/v1.0"

THREADS_SCOPES = "threads_basic,threads_content_publish"
OAUTH_STATE_SESSION_KEY = "threads_oauth_state"


@login_required
def accounts(request):
    """Threads account management page."""
    context = {
        "threads_accounts": request.user.threads_accounts.all(),
        "active_page": "settings",
    }
    return render(request, "threads/accounts.html", context)


@login_required
def connect_threads(request):
    """Kick off the Threads OAuth flow."""
    if not settings.THREADS_APP_ID:
        logger.error("Cannot connect Threads: THREADS_APP_ID is not configured")
        messages.error(request, "Threads is not configured. Please contact support.")
        return redirect("threads:accounts")

    state = secrets.token_urlsafe(32)
    request.session[OAUTH_STATE_SESSION_KEY] = state

    params = {
        "client_id": settings.THREADS_APP_ID,
        "redirect_uri": settings.THREADS_REDIRECT_URI,
        "scope": THREADS_SCOPES,
        "response_type": "code",
        "state": state,
    }
    return redirect(f"{THREADS_AUTHORIZE_URL}?{urlencode(params)}")


@login_required
def threads_callback(request):
    """Handle the OAuth redirect back from Threads."""
    oauth_error = request.GET.get("error")
    if oauth_error:
        error_description = request.GET.get("error_description", oauth_error)
        logger.warning(f"Threads OAuth error for user {request.user.email}: {error_description}")
        messages.error(request, f"Threads authorization was cancelled or denied: {error_description}")
        return redirect("threads:accounts")

    expected_state = request.session.pop(OAUTH_STATE_SESSION_KEY, None)
    received_state = request.GET.get("state")
    if not received_state or not expected_state or received_state != expected_state:
        logger.warning(f"Threads OAuth state mismatch for user {request.user.email}")
        messages.error(request, "Threads authorization failed: invalid or expired request. Please try again.")
        return redirect("threads:accounts")

    code = request.GET.get("code")
    if not code:
        logger.warning(f"Threads OAuth callback missing code for user {request.user.email}")
        messages.error(request, "Threads authorization failed: missing authorization code.")
        return redirect("threads:accounts")

    # Step 1: exchange the authorization code for a short-lived token
    try:
        token_resp = requests.post(
            THREADS_TOKEN_URL,
            data={
                "client_id": settings.THREADS_APP_ID,
                "client_secret": settings.THREADS_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.THREADS_REDIRECT_URI,
                "code": code,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        logger.error(f"Threads short-lived token exchange failed for user {request.user.email}: {e}")
        messages.error(request, "Could not reach Threads. Please try again.")
        return redirect("threads:accounts")

    if token_resp.status_code != 200:
        logger.error(f"Threads short-lived token exchange returned {token_resp.status_code}: {token_resp.text[:500]}")
        messages.error(request, "Failed to connect your Threads account. Please try again.")
        return redirect("threads:accounts")

    try:
        token_data = token_resp.json()
    except ValueError:
        logger.error(f"Threads short-lived token exchange returned invalid JSON: {token_resp.text[:500]}")
        messages.error(request, "Failed to connect your Threads account. Please try again.")
        return redirect("threads:accounts")

    short_lived_token = token_data.get("access_token")
    threads_user_id = token_data.get("user_id")

    if not short_lived_token or not threads_user_id:
        logger.error(f"Threads short-lived token response missing fields: {sorted(token_data.keys())}")
        messages.error(request, "Failed to connect your Threads account. Please try again.")
        return redirect("threads:accounts")

    # Step 2: exchange the short-lived token for a long-lived token (~60 days)
    try:
        exchange_resp = requests.get(
            THREADS_EXCHANGE_URL,
            params={
                "grant_type": "th_exchange_token",
                "client_secret": settings.THREADS_APP_SECRET,
                "access_token": short_lived_token,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        # Do not log the exception body: the URL query carries client_secret/token
        logger.error(f"Threads long-lived token exchange failed for user {request.user.email}: {type(e).__name__}")
        messages.error(request, "Could not reach Threads. Please try again.")
        return redirect("threads:accounts")

    if exchange_resp.status_code != 200:
        logger.error(f"Threads long-lived token exchange returned {exchange_resp.status_code}: {exchange_resp.text[:500]}")
        messages.error(request, "Failed to connect your Threads account. Please try again.")
        return redirect("threads:accounts")

    try:
        exchange_data = exchange_resp.json()
    except ValueError:
        logger.error(f"Threads long-lived token exchange returned invalid JSON: {exchange_resp.text[:500]}")
        messages.error(request, "Failed to connect your Threads account. Please try again.")
        return redirect("threads:accounts")

    long_lived_token = exchange_data.get("access_token")
    expires_in = exchange_data.get("expires_in")

    if not long_lived_token:
        logger.error(f"Threads long-lived token exchange missing access_token: {exchange_data}")
        messages.error(request, "Failed to connect your Threads account. Please try again.")
        return redirect("threads:accounts")

    if not isinstance(expires_in, int) or expires_in < 3600:
        logger.warning(f"Invalid or missing expires_in from Threads: {expires_in}. Defaulting to 60 days.")
        expires_in = 60 * 86400

    # Step 3: fetch the Threads username for display purposes
    username = ""
    try:
        me_resp = requests.get(
            f"{THREADS_GRAPH_BASE}/me",
            params={"fields": "id,username", "access_token": long_lived_token},
            timeout=15,
        )
        if me_resp.status_code == 200:
            username = me_resp.json().get("username", "")
        else:
            logger.warning(f"Threads profile lookup returned {me_resp.status_code}: {me_resp.text[:500]}")
    except requests.RequestException as e:
        logger.warning(f"Threads profile lookup failed for user {request.user.email}: {e}")

    account, created = ThreadsAccount.objects.update_or_create(
        user=request.user,
        threads_user_id=threads_user_id,
        defaults={
            "username": username,
            "access_token": long_lived_token,
            "expires_at": now() + timedelta(seconds=expires_in),
        },
    )
    logger.info(
        f"Threads account {'created' if created else 'updated'} for user {request.user.email}: "
        f"@{username or threads_user_id}"
    )
    messages.success(request, f"Connected Threads account @{username or threads_user_id}.")
    return redirect("threads:accounts")


@login_required
@require_http_methods(["POST"])
def disconnect_threads(request, pk):
    """Delete the user's own Threads account connection."""
    account = get_object_or_404(ThreadsAccount, pk=pk, user=request.user)
    account.delete()

    if "HX-Request" in request.headers:
        return HttpResponse("", status=204)

    messages.success(request, "Threads account disconnected.")
    return redirect("threads:accounts")


def refresh_threads_token(account: ThreadsAccount, retry_count=0, max_retries=3) -> bool:
    """
    Refresh a long-lived Threads token with retry logic for transient failures.
    Mirrors instagram/views.py's refresh_long_lived_token.

    Returns True if refreshed successfully, False otherwise.
    """
    try:
        resp = requests.get(
            THREADS_REFRESH_URL,
            params={
                "grant_type": "th_refresh_token",
                "access_token": account.access_token,
            },
            timeout=10,
        )
    except requests.exceptions.Timeout:
        if retry_count < max_retries:
            logger.warning(
                f"Threads token refresh timeout for {account.username} "
                f"(attempt {retry_count + 1}/{max_retries}). Retrying..."
            )
            wait_time = 2 ** retry_count
            __import__("time").sleep(wait_time)
            return refresh_threads_token(account, retry_count=retry_count + 1, max_retries=max_retries)
        logger.error(f"Threads token refresh failed for {account.username}: Timeout after {max_retries} retries")
        return False
    except requests.exceptions.RequestException as e:
        # Do not log the exception body: the URL query carries the access token
        logger.error(f"Threads token refresh request failed for {account.username}: {type(e).__name__}")
        return False

    if resp.status_code != 200:
        error_text = resp.text[:200]
        if resp.status_code >= 500 and retry_count < max_retries:
            logger.warning(
                f"Transient server error refreshing Threads token for {account.username} "
                f"({resp.status_code}), attempt {retry_count + 1}/{max_retries}. Retrying..."
            )
            wait_time = 2 ** retry_count
            __import__("time").sleep(wait_time)
            return refresh_threads_token(account, retry_count=retry_count + 1, max_retries=max_retries)

        logger.error(f"Failed to refresh Threads token for {account.username}: HTTP {resp.status_code} - {error_text}")
        return False

    try:
        data = resp.json()
    except ValueError:
        logger.error(f"Invalid JSON response refreshing Threads token for {account.username}")
        return False

    new_token = data.get("access_token")
    expires_in = data.get("expires_in")

    if not new_token:
        logger.error(f"No access_token in Threads refresh response for {account.username}")
        return False

    if not isinstance(expires_in, int) or expires_in < 3600:
        logger.warning(f"Invalid or missing expires_in for {account.username}: {expires_in}. Using default 60 days.")
        expires_in = 60 * 86400

    try:
        account.access_token = new_token
        account.expires_at = now() + timedelta(seconds=expires_in)
        account.save(update_fields=["access_token", "expires_at"])
        logger.info(f"Successfully refreshed Threads token for {account.username}. Expires in {expires_in // 86400} days.")
        return True
    except Exception as e:
        logger.error(f"Database error while saving refreshed Threads token for {account.username}: {str(e)}")
        return False
