import requests
import logging
from mastodon import Mastodon
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.conf import settings
from .models import MastodonAccount

logger = logging.getLogger("postflow")


@require_http_methods(["GET", "POST"])
def connect_mastodon(request):
    if request.method == "POST":
        instance_url = request.POST.get("instance_url").strip().rstrip("/")
        if not instance_url.startswith("https://"):
            instance_url = f"https://{instance_url}"

        client_id, client_secret = Mastodon.create_app(
                client_name="PostFlow",
                scopes=["read", "write"],
                redirect_uris=settings.REDIRECT_URI,
                website="https://postflow.photo",
                api_base_url=f"{instance_url}",
                )

        if client_id is not None:
            request.session["mastodon_instance"] = instance_url
            request.session["mastodon_client_id"] = client_id
            request.session["mastodon_client_secret"] = client_secret

            query_params = {
                "client_id": client_id,
                "scope": "read write write:media",
                "redirect_uri": settings.REDIRECT_URI,  # Keep this unchanged
                "response_type": "code",
            }
            logger.debug(query_params)
            logger.debug(settings.REDIRECT_URI)
            auth_url = f"{instance_url}/oauth/authorize?client_id={client_id}&scope=read+write&redirect_uri={settings.REDIRECT_URI}&response_type=code"
            logger.debug(auth_url)
            return redirect(auth_url)

    return redirect("accounts")


@login_required
@require_http_methods(["GET", "POST"])
def mastodon_callback(request):
    instance_url = request.session.get("mastodon_instance")
    client_id = request.session.get("mastodon_client_id")
    client_secret = request.session.get("mastodon_client_secret")
    code = request.GET.get("code")

    if not instance_url or not code:
        return redirect("accounts")

    # Define the correct redirect URI again
    # REDIRECT_URI = request.build_absolute_uri("/mastodon/callback/")

    # Step 3: Exchange code for access token
    token_response = requests.post(f"{instance_url}/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": settings.REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code
    })

    if token_response.status_code == 200:
        token_data = token_response.json()
        access_token = token_data["access_token"]
        logger.debug(access_token)

        # Step 4: Fetch user's Mastodon profile
        user_info = requests.get(f"{instance_url}/api/v1/accounts/verify_credentials", headers={
            "Authorization": f"Bearer {access_token}"
        }).json()

        account = MastodonAccount.objects.create(
            user=request.user,
            instance_url=instance_url,
            access_token=access_token,
            username=user_info["username"]
        )

        # Auto-sync historical posts for new accounts
        # Check if it's a Pixelfed instance (not just Mastodon-compatible)
        is_pixelfed = "pixelfed" in instance_url.lower()

        if is_pixelfed:
            logger.info(f"New Pixelfed account connected, syncing historical posts for @{account.username}")
            try:
                from django.core.management import call_command
                call_command('sync_pixelfed_posts', account_id=account.id, limit=40)
                logger.info(f"Successfully synced Pixelfed posts for @{account.username}")
            except Exception as e:
                logger.error(f"Error syncing Pixelfed posts: {e}")
                # Don't fail the connection if sync fails

    return redirect("accounts")


@login_required
@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def disconnect_mastodon(request, account_id):
    """Delete the user's Mastodon account connection."""
    account = get_object_or_404(MastodonAccount, id=account_id, user=request.user)

    if request.method == "DELETE":
        account.delete()

        # If it's an HTMX request, return a blank response to remove the element
        if "HX-Request" in request.headers:
            return HttpResponse("", status=204)

    return redirect("accounts")
