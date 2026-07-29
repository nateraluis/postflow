import logging
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import LinkedInAccount

logger = logging.getLogger("postflow")

LINKEDIN_AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_SCOPE = "openid profile w_member_social"
LINKEDIN_SESSION_STATE_KEY = "linkedin_oauth_state"
DEFAULT_EXPIRES_IN = 60 * 24 * 3600  # LinkedIn tokens are ~60 days; used only if expires_in is missing


@login_required
def connect_linkedin(request):
    """Redirects the user to LinkedIn's OAuth authorization screen."""
    state = secrets.token_urlsafe(24)
    request.session[LINKEDIN_SESSION_STATE_KEY] = state

    query_params = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "scope": LINKEDIN_SCOPE,
        "state": state,
    }
    auth_url = f"{LINKEDIN_AUTHORIZATION_URL}?{urlencode(query_params)}"
    return redirect(auth_url)


@login_required
def linkedin_callback(request):
    """Handles LinkedIn's OAuth redirect: verifies state, exchanges the code
    for an access token, fetches the member profile, and stores/updates the
    LinkedInAccount. Never raises — all failure paths redirect with a message.
    """
    oauth_error = request.GET.get("error")
    if oauth_error:
        logger.error(f"LinkedIn OAuth error: {oauth_error} - {request.GET.get('error_description')}")
        messages.error(request, "LinkedIn authorization was cancelled or failed.")
        return redirect("linkedin:accounts")

    state = request.GET.get("state")
    expected_state = request.session.pop(LINKEDIN_SESSION_STATE_KEY, None)
    if not state or not expected_state or state != expected_state:
        logger.error("LinkedIn OAuth callback rejected: state mismatch")
        messages.error(request, "LinkedIn authorization failed (invalid state). Please try again.")
        return redirect("linkedin:accounts")

    code = request.GET.get("code")
    if not code:
        logger.error("LinkedIn OAuth callback missing authorization code")
        messages.error(request, "LinkedIn authorization failed (missing code). Please try again.")
        return redirect("linkedin:accounts")

    try:
        token_response = requests.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", DEFAULT_EXPIRES_IN)

        userinfo_response = requests.get(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

        member_id = userinfo["sub"]
        member_urn = f"urn:li:person:{member_id}"
        name = userinfo.get("name", "")

        LinkedInAccount.objects.update_or_create(
            user=request.user,
            member_urn=member_urn,
            defaults={
                "access_token": access_token,
                "username": name,
                "expires_at": timezone.now() + timezone.timedelta(seconds=expires_in),
            },
        )
        logger.info(f"Connected LinkedIn account for user {request.user} - {member_urn}")
        messages.success(request, f"Connected LinkedIn account{f' for {name}' if name else ''}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"LinkedIn OAuth token/profile exchange failed: {str(e)}")
        messages.error(request, "Could not connect your LinkedIn account. Please try again.")
    except (KeyError, ValueError) as e:
        logger.error(f"LinkedIn OAuth response parsing failed: {str(e)}")
        messages.error(request, "Could not connect your LinkedIn account. Please try again.")
    except Exception:
        logger.exception("Unexpected error during LinkedIn OAuth callback")
        messages.error(request, "Could not connect your LinkedIn account. Please try again.")

    return redirect("linkedin:accounts")


@login_required
def accounts(request):
    """Management page listing the user's connected LinkedIn accounts."""
    linkedin_accounts = request.user.linkedin_accounts.all()
    return render(
        request,
        "linkedin/accounts.html",
        {
            "linkedin_accounts": linkedin_accounts,
            "active_page": "settings",
        },
    )


@login_required
@require_POST
def disconnect_linkedin(request, pk):
    """Deletes one of the current user's own LinkedIn accounts."""
    account = get_object_or_404(LinkedInAccount, pk=pk, user=request.user)
    account.delete()
    messages.success(request, "LinkedIn account disconnected.")
    return redirect("linkedin:accounts")
