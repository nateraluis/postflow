import os
import base64
import hmac
import hashlib
import uuid
import json
import requests
import logging
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.conf import settings
from django.utils.timezone import now
from .models import InstagramBusinessAccount

logger = logging.getLogger("postflow")


def refresh_long_lived_token(account: InstagramBusinessAccount, retry_count=0, max_retries=3) -> bool:
    """
    Refresh a long-lived Instagram token with retry logic.

    Args:
        account: InstagramBusinessAccount instance to refresh
        retry_count: Current retry attempt number (internal use)
        max_retries: Maximum number of retry attempts for transient failures

    Returns True if refreshed successfully, False otherwise.
    """
    refresh_url = "https://graph.instagram.com/refresh_access_token"

    try:
        resp = requests.get(refresh_url, params={
            "grant_type": "ig_refresh_token",
            "access_token": account.access_token,
        }, timeout=10)
    except requests.exceptions.Timeout:
        if retry_count < max_retries:
            logger.warning(f"Token refresh timeout for {account.username} (attempt {retry_count + 1}/{max_retries}). Retrying...")
            # Exponential backoff: 1s, 2s, 4s
            wait_time = 2 ** retry_count
            __import__('time').sleep(wait_time)
            return refresh_long_lived_token(account, retry_count=retry_count + 1, max_retries=max_retries)
        else:
            logger.error(f"Token refresh failed for {account.username}: Timeout after {max_retries} retries")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Token refresh request failed for {account.username}: {str(e)}")
        return False

    # Handle non-200 responses
    if resp.status_code != 200:
        try:
            error_data = resp.json()
            error_msg = error_data.get("error", {})
            error_type = error_msg.get("type") if isinstance(error_msg, dict) else str(error_msg)
            error_message = error_msg.get("message", "Unknown error") if isinstance(error_msg, dict) else str(error_msg)
        except (ValueError, KeyError):
            error_type = "unknown"
            error_message = resp.text[:200]  # Limit error text length

        # Check if error is authentication-related (token revoked, invalid, etc.)
        auth_error_indicators = ["OAuthException", "Invalid OAuth access token", "revoked", "expired"]
        is_auth_error = any(indicator.lower() in (error_type.lower() or error_message.lower()) for indicator in auth_error_indicators)

        if is_auth_error:
            logger.error(f"Authentication error for {account.username}: {error_type} - {error_message}. Token may be revoked.")
            # Mark account as having auth issues but don't retry
            return False

        # Transient errors: 500, 502, 503, 504 - retry these
        if resp.status_code >= 500 and retry_count < max_retries:
            logger.warning(f"Transient server error for {account.username} ({resp.status_code}), attempt {retry_count + 1}/{max_retries}. Retrying...")
            wait_time = 2 ** retry_count
            __import__('time').sleep(wait_time)
            return refresh_long_lived_token(account, retry_count=retry_count + 1, max_retries=max_retries)

        logger.error(f"Failed to refresh token for {account.username}: HTTP {resp.status_code} - {error_type}: {error_message}")
        return False

    # Parse and validate response
    try:
        data = resp.json()
    except ValueError:
        logger.error(f"Invalid JSON response from Instagram API for {account.username}")
        return False

    new_token = data.get("access_token")
    expires_in = data.get("expires_in")  # seconds

    # Validate token response
    if not new_token:
        logger.error(f"No access_token in response for {account.username}")
        return False

    if not expires_in or not isinstance(expires_in, int) or expires_in < 3600:
        logger.warning(f"Invalid or missing expires_in for {account.username}: {expires_in}. Using default 60 days.")
        expires_in = 60 * 86400  # Default to 60 days if missing

    try:
        account.access_token = new_token
        account.expires_at = now() + timedelta(seconds=expires_in)
        account.last_refreshed_at = now()
        account.save(update_fields=["access_token", "expires_at", "last_refreshed_at"])
        logger.info(f"Successfully refreshed token for {account.username}. Expires in {expires_in // 86400} days.")
        return True
    except Exception as e:
        logger.error(f"Database error while saving refreshed token for {account.username}: {str(e)}")
        return False


@login_required
@require_http_methods(["GET", "POST"])
def connect_instagram(request):
    if request.method == "POST":
        base_url = "https://www.instagram.com/oauth/authorize"
        params = {
            "enable_fb_login": "0",
            "force_authentication": "1",
            "client_id": settings.FACEBOOK_APP_ID,
            "redirect_uri": settings.INSTAGRAM_BUSINESS_REDIRECT_URI,
            "response_type": "code",
            "scope": (
                "instagram_business_basic,"
                "instagram_business_manage_messages,"
                "instagram_business_manage_comments,"
                "instagram_business_content_publish,"
                "instagram_business_manage_insights"
            ),
        }

        # url = f"{base_url}?{urllib.parse.urlencode(params)}"
        url = f"https://www.instagram.com/oauth/authorize?enable_fb_login=0&force_authentication=1&client_id=1370425837536915&redirect_uri={settings.INSTAGRAM_BUSINESS_REDIRECT_URI}&response_type=code&scope=instagram_business_basic%2Cinstagram_business_manage_messages%2Cinstagram_business_manage_comments%2Cinstagram_business_content_publish%2Cinstagram_business_manage_insights"
        return redirect(url)

    return redirect("accounts")


@csrf_exempt
def facebook_webhook(request):
    if request.method == "GET":
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if verify_token == settings.FACEBOOK_VERIFY_TOKEN:
            return HttpResponse(challenge)
        return HttpResponse("Invalid verify token", status=403)

    elif request.method == "POST":
        # Incoming data from Facebook (e.g. media, comments, etc.)
        data = request.body
        # Optionally parse JSON and handle it
        # For now, just acknowledge
        return JsonResponse({"status": "received"})

    return HttpResponse(status=405)


@login_required
def instagram_business_callback(request):
    code = request.GET.get("code")
    if not code:
        return render(request, "error.html", {"message": "Missing authorization code."})

    # Step 1: Exchange code for short-lived access token
    token_url = "https://api.instagram.com/oauth/access_token"
    token_resp = requests.post(token_url, data={
        "client_id": settings.FACEBOOK_APP_ID,
        "client_secret": settings.FACEBOOK_APP_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": settings.INSTAGRAM_BUSINESS_REDIRECT_URI,
        "code": code,
    })

    if token_resp.status_code != 200:
        return HttpResponse(
                f"Failed to get access token:<br>Status: {token_resp.status_code}<br>Response: {token_resp.text}",
                status=token_resp.status_code,
                content_type="text/html"
                )
    short_lived_token = token_resp.json().get("access_token")

    # Step 2: Exchange short-lived for LONG-LIVED token
    exchange_url = "https://graph.instagram.com/access_token"
    exchange_resp = requests.get(exchange_url, params={
        "grant_type": "ig_exchange_token",
        "client_secret": settings.FACEBOOK_APP_SECRET,
        "access_token": short_lived_token,
    })
    if exchange_resp.status_code != 200:
        return HttpResponse(
            f"⚠️ Failed to exchange for long-lived token:<br>Status: {exchange_resp.status_code}<br>Response: {exchange_resp.text}",
            status=exchange_resp.status_code,
            content_type="text/html"
        )

    exchange_data = exchange_resp.json()
    long_lived_token = exchange_data.get("access_token")
    expires_in = exchange_data.get("expires_in")  # seconds

    if not long_lived_token:
        return HttpResponse(
            f"⚠️ Failed to get long-lived token from exchange:<br>Response: {exchange_resp.text}",
            status=400,
            content_type="text/html"
        )

    # Get instagram User
    ig_resp = requests.get(
        f"https://graph.instagram.com/v22.0/me",
        params={
            "fields": "user_id,username",
            "access_token": long_lived_token,
        }
    )

    if ig_resp.status_code != 200:
        return HttpResponse(
                f"⚠️ Failed to fetch Instagram user data:<br>Status: {ig_resp.status_code}<br>Response: {ig_resp.text}",
                status=ig_resp.status_code,
                content_type="text/html"
                )
    data = ig_resp.json()
    logger.info(f"Instagram user data retrieved: {data.get('username')}")

    # Calculate actual token expiration - use expires_in from exchange if available, default to 60 days
    if expires_in and isinstance(expires_in, int) and expires_in > 3600:
        token_expires_at = now() + timedelta(seconds=expires_in)
        logger.info(f"Token expires in {expires_in // 86400} days")
    else:
        token_expires_at = now() + timedelta(days=60)
        logger.warning(f"No valid expires_in received, defaulting to 60 days")

    account, created = InstagramBusinessAccount.objects.update_or_create(
        user=request.user,
        instagram_id=data.get("user_id"),
        defaults={
            "instagram_id": data.get("user_id"),
            "username": data.get("username"),
            "access_token": long_lived_token,
            "expires_at": token_expires_at,
        }
    )
    logger.info(f"Instagram account {'created' if created else 'updated'} for user {request.user.email}: {data.get('username')}")

    # Auto-sync historical posts and fetch engagement for new accounts
    if created:
        logger.info(f"New Instagram account connected, syncing historical posts for @{account.username}")
        try:
            from django.core.management import call_command
            call_command('sync_instagram_posts', account_id=account.id, limit=50)
            logger.info(f"Fetching insights for new Instagram account @{account.username}")
            call_command('fetch_instagram_insights', account_id=account.id, limit=30)
            logger.info(f"Successfully synced Instagram posts for @{account.username}")
        except Exception as e:
            logger.error(f"Error syncing Instagram posts: {e}")
            # Don't fail the connection if sync fails

    return redirect("accounts")


def parse_signed_request(signed_request, app_secret):
    try:
        encoded_sig, payload = signed_request.split('.', 1)
        sig = base64.urlsafe_b64decode(encoded_sig + "==")
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))

        expected_sig = hmac.new(
            key=app_secret.encode(),
            msg=payload.encode(),
            digestmod=hashlib.sha256
        ).digest()

        if not hmac.compare_digest(sig, expected_sig):
            return None
        return data
    except Exception:
        return None


@csrf_exempt
def instagram_deauthorize(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    signed_request = request.POST.get("signed_request")
    data = parse_signed_request(signed_request, settings.FACEBOOK_APP_SECRET)
    if not data:
        return HttpResponseBadRequest("Invalid signature")

    user_id = data.get("user_id")
    if not user_id:
        return HttpResponseBadRequest("Missing user_id")

    # Remove InstagramBusinessAccount(s) for this user_id
    InstagramBusinessAccount.objects.filter(instagram_id=user_id).delete()

    return JsonResponse({"success": True})


@csrf_exempt
def instagram_data_deletion(request):
    signed_request = request.POST.get("signed_request")
    data = parse_signed_request(signed_request, settings.FACEBOOK_APP_SECRET)
    if not data:
        return HttpResponseBadRequest("Invalid signature")

    user_id = data.get("user_id")
    confirmation_code = str(uuid.uuid4())

    # Delete data for user
    InstagramBusinessAccount.objects.filter(instagram_id=user_id).delete()

    # Respond with confirmation and optional status page
    return JsonResponse({
        "confirmation_code": confirmation_code
    })


@login_required
@require_http_methods(["POST"])
def disconnect_instagram(request, account_id):
    """Delete the user's Instagram account connection."""
    account = get_object_or_404(InstagramBusinessAccount, user=request.user, id=account_id)

    if request.method == "POST":
        account.delete()

        # If it's an HTMX request, return a blank response to remove the element
        if "HX-Request" in request.headers:
            return HttpResponse("", status=204)

    return redirect("accounts")
