import requests
import logging
from mastodon import Mastodon
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django.conf import settings
from .models import MastodonAccount

logger = logging.getLogger("postflow")


@require_http_methods(["GET", "POST"])
def connect_mastodon(request):
    """Initiate Mastodon OAuth flow"""
    if request.method == "POST":
        instance_url = request.POST.get("instance_url", "").strip().rstrip("/")
        if not instance_url.startswith("https://"):
            instance_url = f"https://{instance_url}"

        try:
            client_id, client_secret = Mastodon.create_app(
                client_name="PostFlow",
                scopes=["read", "write", "write:media"],
                redirect_uris=settings.REDIRECT_URI,
                website="https://postflow.photo",
                api_base_url=instance_url,
            )

            if client_id is not None:
                request.session["mastodon_instance"] = instance_url
                request.session["mastodon_client_id"] = client_id
                request.session["mastodon_client_secret"] = client_secret

                auth_url = f"{instance_url}/oauth/authorize?client_id={client_id}&scope=read+write+write:media&redirect_uri={settings.REDIRECT_URI}&response_type=code"
                logger.debug(f"Redirecting to Mastodon auth URL: {auth_url}")
                return redirect(auth_url)
            else:
                logger.error("Failed to create Mastodon app")
        except Exception as e:
            logger.error(f"Error initiating Mastodon OAuth: {str(e)}")

    return redirect("accounts")


@login_required
@require_http_methods(["GET"])
def mastodon_callback(request):
    """Handle Mastodon OAuth callback"""
    code = request.GET.get("code")
    instance_url = request.session.get("mastodon_instance")
    client_id = request.session.get("mastodon_client_id")
    client_secret = request.session.get("mastodon_client_secret")

    if not all([code, instance_url, client_id, client_secret]):
        logger.error("Missing OAuth parameters in Mastodon callback")
        return redirect("accounts")

    try:
        # Exchange code for access token
        mastodon = Mastodon(
            client_id=client_id,
            client_secret=client_secret,
            api_base_url=instance_url,
        )

        access_token = mastodon.log_in(
            username=None,  # We'll get this from verify_credentials
            password=None,
            scopes=["read", "write", "write:media"],
            code=code,
            redirect_uri=settings.REDIRECT_URI,
        )

        # Get user info
        user_info = mastodon.account_verify_credentials()
        username = user_info.get("username", user_info.get("acct", "unknown"))

        # Create or update account
        account, created = MastodonAccount.objects.update_or_create(
            user=request.user,
            instance_url=instance_url,
            defaults={
                "username": username,
                "access_token": access_token,
            }
        )

        action = "connected" if created else "updated"
        logger.info(f"Mastodon account {action}: {username}@{instance_url}")

    except Exception as e:
        logger.error(f"Error in Mastodon callback: {str(e)}")

    # Clear session data
    request.session.pop("mastodon_instance", None)
    request.session.pop("mastodon_client_id", None)
    request.session.pop("mastodon_client_secret", None)

    return redirect("accounts")


@login_required
@require_http_methods(["DELETE"])
def disconnect_mastodon(request, account_id):
    """Disconnect a Mastodon account"""
    account = get_object_or_404(MastodonAccount, id=account_id, user=request.user)
    username = account.username
    instance_url = account.instance_url
    account.delete()
    logger.info(f"Disconnected Mastodon account: {username}@{instance_url}")
    return HttpResponse(status=204)
