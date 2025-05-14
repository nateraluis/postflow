import os
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
from django.http import HttpResponse
from .forms import CustomUserCreationForm, CustomAuthenticationForm
from .models import Tag, TagGroup, MastodonAccount, ScheduledPost
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
def signup(request):
    form=CustomUserCreationForm()
    context = {"form": form}
    return render(request, "postflow/signup.html", context)


@require_http_methods(["POST"])
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

    # Group posts by date
    grouped_posts = defaultdict(list)
    for post in scheduled_posts:
        grouped_posts[post.post_date.date()].append(post)

    context = {
        "hours": range(0, 24),
        "minutes": range(0, 60, 5),
        "hashtag_groups": TagGroup.objects.filter(user=request.user),
        "mastodon_accounts": MastodonAccount.objects.filter(user=request.user),
        "instagram_accounts": None,
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
        localized_datetime = user_tz.localize(datetime.strptime(scheduled_datetime, "%Y-%m-%d %H:%M:%S"))
        utc_datetime = localized_datetime.astimezone(pytz.UTC)

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
        # Handle Instagram connection logic here
        pass

    return redirect("dashboard")
