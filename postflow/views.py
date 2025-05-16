import os
import base64
import hmac
import hashlib
import uuid
from django.utils.timezone import make_aware
import json
from django.db import IntegrityError
import requests
from mastodon import Mastodon
from django.shortcuts import render
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from .forms import CustomUserCreationForm, CustomAuthenticationForm
from .models import Tag, TagGroup, MastodonAccount, ScheduledPost, InstagramBusinessAccount
from .utils import get_s3_signed_url, upload_to_s3, post_pixelfed
import pytz
from datetime import datetime, timedelta
from collections import defaultdict
from django.conf import settings
import logging

logger = logging.getLogger("postflow")


def _validate_user(request, username):
    user = request.user
    if username != user.username:
        return redirect("login")
    return user


def index(request):
    return render(request, "postflow/landing_page.html")


def login_view(request):
    if request.method == "POST":
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect("profile", username=username)
            else:
                form.add_error("username", "Invalid email or password")
    else:
        form = CustomAuthenticationForm()
    context = {"form": form}
    return render(request, "postflow/login.html", context)


def logout_view(request):
    return redirect("login")


@require_http_methods(["GET", "POST"])
def register(request):
    context = {}
    form = CustomUserCreationForm()
    context["form"] = form
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            logger.debug("👤 User saved to DB:", user)
            username = form.cleaned_data["email"]
            user = authenticate(
                username=username,
                password=form.cleaned_data["password1"],
            )
            if user:
                login(request, user)
            else:
                logger.debug("❌ Authentication failed for:", username)
            return redirect("profile", username=username)
        else:
            logger.debug("❌ Form is invalid. Errors:", form.errors)
            context["form"] = form
    return render(request, "postflow/signup.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request, username):
    user = _validate_user(request, username)
    context = {"profile_user": user}
    return render(request, "postflow/pages/dashboard.html", context)

@login_required
@require_http_methods(["GET"])
def dashboard(request):
    if request.headers.get("HX-Request"):
        return render(request, 'postflow/components/dashboard.html')
    return render(request, 'postflow/pages/dashboard.html')


@login_required
@require_http_methods(["GET"])
def calendar_view(request):
    today = datetime.today().date()
    scheduled_posts = ScheduledPost.objects.filter(
        user=request.user, post_date__date__gte=today
    ).prefetch_related("hashtag_groups__tags").order_by("post_date")


    # Generate signed URLs for images
    for post in scheduled_posts:
        post.image_url = get_s3_signed_url(post.image.name)
        post.hashtags = list(Tag.objects.filter(tag_groups__in=post.hashtag_groups.all()).distinct())
        # update the post date to the user timezone

    # Group posts by date
    grouped_posts = defaultdict(list)
    for post in scheduled_posts:
        grouped_posts[post.post_date.date()].append(post)

    context = {
        "hours": range(0, 24),
        "minutes": range(0, 60, 5),
        "hashtag_groups": TagGroup.objects.filter(user=request.user),
        "mastodon_accounts": MastodonAccount.objects.filter(user=request.user),
        "instagram_accounts": InstagramBusinessAccount.objects.filter(user=request.user),
        "grouped_posts": dict(grouped_posts),  # Convert defaultdict to dict
    }

    if "HX-Request" in request.headers:
        return render(request, "postflow/components/schedule_posts.html", context)

    return render(request, "postflow/pages/calendar.html", context)

@login_required
@require_http_methods(["POST"])
def schedule_post(request):
    user_timezone = request.POST.get("user_timezone", "UTC")
    post_date = request.POST.get("post_date")
    post_hour = request.POST.get("post_hour")
    post_minute = request.POST.get("post_minute")
    caption = request.POST.get("caption", "")
    hashtag_group_ids = request.POST.getlist("hashtag_groups")
    mastodon_account_ids = request.POST.getlist("social_accounts")
    image = request.FILES.get("photo")

    context = {
        "hours": range(0, 24),
        "minutes": range(0, 60, 5),
        "hashtag_groups": TagGroup.objects.filter(user=request.user),
        "mastodon_accounts": MastodonAccount.objects.filter(user=request.user),
        "instagram_accounts": None,
    }

    # Validation: Ensure an image is uploaded
    if not image:
        context["error"] = "Please select an image to post."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        return response

    # Validation: Ensure date & time are selected
    if not post_date or not post_hour or not post_minute:
        context["error"] = "Please select a valid date and time."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        logger.error("Invalid date and time selected.")
        return response

    # Convert user-selected date & time to UTC
    try:
        scheduled_datetime = f"{post_date} {post_hour}:{post_minute}:00"
        user_tz = pytz.timezone(user_timezone)
        naive_dt = datetime.strptime(scheduled_datetime, "%Y-%m-%d %H:%M:%S")
        localized_datetime = user_tz.localize(naive_dt)
        utc_datetime = localized_datetime.astimezone(pytz.UTC)
        print(utc_datetime)

    except Exception as e:
        context["error"] = "Invalid date and time selected."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        logger.error(f"Invalid date and time: {e}")
        return response

    # Ensure the scheduled time is in the future (at least 5 min)
    current_utc_time = now()
    min_allowed_time = current_utc_time + timedelta(minutes=5)

    if utc_datetime < min_allowed_time:
        context["error"] = "The scheduled time must be at least 5 minutes in the future."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        logger.error(f"Invalid scheduled time: {utc_datetime}")
        return response

    # Save the uploaded image and create the ScheduledPost
    try:
        filename, file_extension = os.path.splitext(image.name)
        unique_filename = f"user_{request.user.id}_{int(datetime.utcnow().timestamp())}{file_extension}"
        file_path = os.path.join("scheduled_posts", unique_filename)

        saved_path = upload_to_s3(image, file_path)
        if not saved_path:
            context["error"] = "Failed to upload the image to S3."
            response = render(request, "postflow/components/upload_photo_form.html", context)
            response['HX-Retarget'] = '#form-container'
            logger.error("Failed to upload the image to S3.")
            return response

        scheduled_post = ScheduledPost.objects.create(
            user=request.user,
            image=saved_path,
            caption=caption,
            post_date=utc_datetime,
            user_timezone=user_timezone,
        )
        logger.info(f"New Scheduled Post created: {scheduled_post}")


        scheduled_post.hashtag_groups.set(TagGroup.objects.filter(id__in=hashtag_group_ids))
        scheduled_post.mastodon_accounts.set(MastodonAccount.objects.filter(id__in=mastodon_account_ids))
        logger.info(f"Hashtag groups and Mastodon accounts added to post: {scheduled_post}")

        # Refresh grouped posts to update calendar component
        scheduled_posts = ScheduledPost.objects.filter(
            user=request.user, post_date__date__gte=current_utc_time.date()
        ).prefetch_related("hashtag_groups__tags", "mastodon_accounts").order_by("post_date")
        logger.info(f"Refreshing grouped posts for calendar view: {scheduled_posts}")

        # Post to pixelfed
        # post_pixelfed(scheduled_post, saved_path)
        # logger.info(f"Post scheduled on Mastodon: {scheduled_post}")

        # Group posts by date
        grouped_posts = defaultdict(list)
        for post in scheduled_posts:
            post.image_url = get_s3_signed_url(post.image.name)
            post.hashtags = list(Tag.objects.filter(tag_groups__in=post.hashtag_groups.all()).distinct())
            grouped_posts[post.post_date.date()].append(post)

        calendar_context = {"grouped_posts": dict(grouped_posts)}
        logger.info(f"Post scheduled successfully: {scheduled_post}")
        return render(request, "postflow/components/calendar.html", calendar_context)


    except Exception as e:
        context["error"] = "An error occurred while scheduling the post."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        logger.error(f"Error scheduling post: {e}")
        return response


@login_required
@require_http_methods(["GET", "POST"])
def hashtag_groups_view(request):
    """Handles hashtag group creation and displays groups dynamically."""

    user = request.user

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        hashtag_text = request.POST.get("hashtags", "").strip()

        if name and hashtag_text:
            try:
                group, created = TagGroup.objects.get_or_create(name=name, user=user)

                # Process hashtags (split by spaces or commas)
                hashtags = [h.strip() for h in hashtag_text.replace(",", " ").split() if h.strip()]
                for hashtag_name in hashtags:
                    hashtag, _ = Tag.objects.get_or_create(name=hashtag_name, user=user)
                    group.tags.add(hashtag)

                # **HTMX Request Handling: Return Only the New Group Card**
                if "HX-Request" in request.headers:
                    return render(request, "postflow/components/partials/hashtag_group_card.html", {"group": group})

                return redirect("hashtag-groups")

            except IntegrityError:
                # Handle duplicate group error dynamically
                if "HX-Request" in request.headers:
                    return HttpResponse('<script>document.getElementById("error-message").innerText = "Group name already exists!"</script>')

    # Fetch hashtag groups for the logged-in user
    hashtag_groups = TagGroup.objects.filter(user=user).prefetch_related("tags")

    # **HTMX Fix: Load Full Hashtags Component Instead of Just Groups**
    if "HX-Request" in request.headers:
        return render(request, "postflow/components/hashtags.html", {"hashtag_groups": hashtag_groups})

    # **Normal Request: Render Full Page with Sidebar**
    return render(request, "postflow/pages/hashtags.html", {"hashtag_groups": hashtag_groups})


@login_required
@require_http_methods(["GET"])
def hashtag_groups_list_view(request):
    """Returns only the list of hashtag groups (used for HTMX dynamic updates)."""
    user = request.user
    hashtag_groups = TagGroup.objects.filter(user=user).prefetch_related("tags")
    return render(request, "postflow/components/hashtags_groups.html", {"hashtag_groups": hashtag_groups})



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

    return redirect("dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def mastodon_callback(request):
    instance_url = request.session.get("mastodon_instance")
    client_id = request.session.get("mastodon_client_id")
    client_secret = request.session.get("mastodon_client_secret")
    code = request.GET.get("code")

    if not instance_url or not code:
        return redirect("dashboard")
        
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

        MastodonAccount.objects.create(
            user=request.user,
            instance_url=instance_url,
            access_token=access_token,
            username=user_info["username"]
        )

    return redirect("dashboard")

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

    return redirect("dashboard")


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
        url = "https://www.instagram.com/oauth/authorize?enable_fb_login=0&force_authentication=1&client_id=1370425837536915&redirect_uri=https://postflow.photo/accounts/instagram/business/callback/&response_type=code&scope=instagram_business_basic%2Cinstagram_business_manage_messages%2Cinstagram_business_manage_comments%2Cinstagram_business_content_publish%2Cinstagram_business_manage_insights"
        return redirect(url)

    return redirect("dashboard")


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
                f"⚠️ Failed to get access token:<br>Status: {token_resp.status_code}<br>Response: {token_resp.text}",
                status=token_resp.status_code,
                content_type="text/html"
                )
    access_token = token_resp.json().get("access_token")

    # Get instagram User
    ig_resp = requests.get(
        f"https://graph.instagram.com/v22.0/me",
        params={
            "fields": "user_id,username",
            "access_token": access_token,
        }
    )

    if ig_resp.status_code != 200:
        return HttpResponse(
                f"⚠️ Failed to fetch Instagram user data:<br>Status: {ig_resp.status_code}<br>Response: {ig_resp.text}",
                status=ig_resp.status_code,
                content_type="text/html"
                )
    data = ig_resp.json()

    InstagramBusinessAccount.objects.update_or_create(
        user=request.user,
        instagram_id=data.get("user_id"),
        defaults={
            "username": data.get("username"),
            "access_token": access_token,
            "page_id": "",  # Optional: you can remove or populate if available separately
        }
    )
    return redirect("dashboard")



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

    return redirect("dashboard")
