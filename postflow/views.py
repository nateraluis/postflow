import os
from django.utils.timezone import make_aware
from django.db import IntegrityError
from django.shortcuts import render
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from .forms import CustomUserCreationForm, CustomAuthenticationForm
from .models import Tag, TagGroup, ScheduledPost, Subscriber
from .utils import get_s3_signed_url, upload_to_s3
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

            # In DEBUG mode, redirect to accounts instead of pricing
            if settings.DEBUG:
                return redirect("accounts")
            else:
                return redirect("subscriptions:pricing")
        else:
            logger.debug("❌ Form is invalid. Errors:", form.errors)
            context["form"] = form
    return render(request, "postflow/signup.html", context)


@login_required
@require_http_methods(["GET"])
def profile_view(request):
    """Display user profile with account details and statistics."""
    from pixelfed.models import MastodonAccount
    from instagram.models import InstagramBusinessAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount

    user = request.user

    # Get social account counts
    mastodon_count = MastodonAccount.objects.filter(user=user).count()
    mastodon_native_count = MastodonNativeAccount.objects.filter(user=user).count()
    instagram_count = InstagramBusinessAccount.objects.filter(user=user).count()
    total_connected_accounts = mastodon_count + mastodon_native_count + instagram_count

    # Get post statistics
    total_scheduled = ScheduledPost.objects.filter(user=user, status__in=['pending', 'scheduled']).count()
    total_posted = ScheduledPost.objects.filter(user=user, status='posted').count()
    total_failed = ScheduledPost.objects.filter(user=user, status='failed').count()

    # Get subscription information
    subscription = None
    has_subscription = False
    try:
        subscription = user.subscription
        has_subscription = True
    except AttributeError:
        pass

    context = {
        'active_page': 'profile',
        'user': user,
        'mastodon_count': mastodon_count,
        'mastodon_native_count': mastodon_native_count,
        'instagram_count': instagram_count,
        'total_connected_accounts': total_connected_accounts,
        'total_scheduled': total_scheduled,
        'total_posted': total_posted,
        'total_failed': total_failed,
        'subscription': subscription,
        'has_subscription': has_subscription,
    }

    if request.headers.get("HX-Request"):
        # Return both the content and sidebar with OOB swap
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, 'postflow/components/profile.html', context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)

    return render(request, 'postflow/pages/profile.html', context)

@login_required
@require_http_methods(["GET"])
def accounts_view(request):
    context = {'active_page': 'accounts'}
    if request.headers.get("HX-Request"):
        # Return both the content and sidebar with OOB swap
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, 'postflow/components/accounts.html', context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)
    return render(request, 'postflow/pages/accounts.html', context)


@login_required
@require_http_methods(["GET"])
def calendar_view(request):
    # Import here to avoid circular imports
    from pixelfed.models import MastodonAccount
    from instagram.models import InstagramBusinessAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount

    today = datetime.today().date()
    scheduled_posts = ScheduledPost.objects.filter(
        user=request.user, post_date__date__gte=today
    ).prefetch_related("hashtag_groups__tags", "images").order_by("post_date")


    # Generate signed URLs for images
    for post in scheduled_posts:
        # Handle multiple images via PostImage model
        if post.images.exists():
            post.image_urls = [get_s3_signed_url(img.image.name) for img in post.images.all()]
        # Fallback to legacy single image field
        elif post.image:
            post.image_urls = [get_s3_signed_url(post.image.name)]
        else:
            post.image_urls = []

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
        "mastodon_native_accounts": MastodonNativeAccount.objects.filter(user=request.user),
        "instagram_accounts": InstagramBusinessAccount.objects.filter(user=request.user),
        "grouped_posts": dict(grouped_posts),  # Convert defaultdict to dict
        "active_page": "calendar",
    }

    if "HX-Request" in request.headers:
        # Check if this is a toggle request (from the toggle buttons)
        # Toggle buttons target #calendar-view-container, so return only calendar.html
        if request.headers.get("HX-Target") == "calendar-view-container":
            return render(request, "postflow/components/calendar.html", context)
        # Otherwise return full schedule_posts component (for sidebar navigation) + sidebar OOB
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, "postflow/components/schedule_posts.html", context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)

    return render(request, "postflow/pages/calendar.html", context)

@login_required
@require_http_methods(["POST"])
def schedule_post(request):
    # Import here to avoid circular imports
    from pixelfed.models import MastodonAccount
    from instagram.models import InstagramBusinessAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount

    user_timezone = request.POST.get("user_timezone", "UTC")
    post_date = request.POST.get("post_date")
    post_hour = request.POST.get("post_hour")
    post_minute = request.POST.get("post_minute")
    caption = request.POST.get("caption", "")
    hashtag_group_ids = request.POST.getlist("hashtag_groups")
    mastodon_account_ids = request.POST.getlist("social_accounts")
    mastodon_native_account_ids = request.POST.getlist("mastodon_native_accounts")
    instagram_account_ids = request.POST.getlist("instagram_accounts")
    images = request.FILES.getlist("photos")

    context = {
        "hours": range(0, 24),
        "minutes": range(0, 60, 5),
        "hashtag_groups": TagGroup.objects.filter(user=request.user),
        "mastodon_accounts": MastodonAccount.objects.filter(user=request.user),
        "mastodon_native_accounts": MastodonNativeAccount.objects.filter(user=request.user),
        "instagram_accounts": InstagramBusinessAccount.objects.filter(user=request.user),
    }

    # Validation: Ensure at least one image is uploaded
    if not images or len(images) == 0:
        context["error"] = "Please select at least one image to post."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        return response

    # Validation: Ensure no more than 10 images (Instagram carousel limit)
    if len(images) > 10:
        context["error"] = "You can upload a maximum of 10 images per post."
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

    # Ensure the scheduled time is in the future (at least 30 seconds)
    current_utc_time = now()
    min_allowed_time = current_utc_time + timedelta(seconds=30)

    if utc_datetime < min_allowed_time:
        context["error"] = "The scheduled time must be at least 5 minutes in the future."
        response = render(request, "postflow/components/upload_photo_form.html", context)
        response['HX-Retarget'] = '#form-container'
        logger.error(f"Invalid scheduled time: {utc_datetime}")
        return response

    # Save the uploaded images and create the ScheduledPost
    try:
        # First create the ScheduledPost without images
        scheduled_post = ScheduledPost.objects.create(
            user=request.user,
            caption=caption,
            post_date=utc_datetime,
            user_timezone=user_timezone,
        )
        logger.info(f"New Scheduled Post created: {scheduled_post}")

        # Upload and create PostImage records for each image
        from postflow.models import PostImage

        for index, image in enumerate(images):
            filename, file_extension = os.path.splitext(image.name)
            unique_filename = f"user_{request.user.id}_{int(datetime.utcnow().timestamp())}_{index}{file_extension}"
            file_path = os.path.join("scheduled_posts", unique_filename)

            saved_path = upload_to_s3(image, file_path)
            if not saved_path:
                # If any image fails to upload, delete the post and return error
                scheduled_post.delete()
                context["error"] = f"Failed to upload image {index + 1} to S3."
                response = render(request, "postflow/components/upload_photo_form.html", context)
                response['HX-Retarget'] = '#form-container'
                logger.error(f"Failed to upload image {index + 1} to S3.")
                return response

            # Create PostImage record
            PostImage.objects.create(
                scheduled_post=scheduled_post,
                image=saved_path,
                order=index
            )
            logger.info(f"Image {index + 1}/{len(images)} uploaded for post {scheduled_post.id}")


        scheduled_post.hashtag_groups.set(TagGroup.objects.filter(id__in=hashtag_group_ids))
        scheduled_post.mastodon_accounts.set(MastodonAccount.objects.filter(id__in=mastodon_account_ids))
        scheduled_post.mastodon_native_accounts.set(MastodonNativeAccount.objects.filter(id__in=mastodon_native_account_ids))
        scheduled_post.instagram_accounts.set(InstagramBusinessAccount.objects.filter(id__in=instagram_account_ids))
        logger.info(f"Hashtag groups and social accounts added to post: {scheduled_post}")

        # Refresh grouped posts to update calendar component
        scheduled_posts = ScheduledPost.objects.filter(
            user=request.user, post_date__date__gte=current_utc_time.date()
        ).prefetch_related("hashtag_groups__tags", "mastodon_accounts", "images").order_by("post_date")
        logger.info(f"Refreshing grouped posts for calendar view: {scheduled_posts}")

        # Group posts by date
        grouped_posts = defaultdict(list)
        for post in scheduled_posts:
            # Handle multiple images via PostImage model
            if post.images.exists():
                post.image_urls = [get_s3_signed_url(img.image.name) for img in post.images.all()]
            # Fallback to legacy single image field
            elif post.image:
                post.image_urls = [get_s3_signed_url(post.image.name)]
            else:
                post.image_urls = []

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
    context = {"hashtag_groups": hashtag_groups, "active_page": "hashtags"}

    # **HTMX Fix: Load Full Hashtags Component Instead of Just Groups**
    if "HX-Request" in request.headers:
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, "postflow/components/hashtags.html", context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)

    # **Normal Request: Render Full Page with Sidebar**
    return render(request, "postflow/pages/hashtags.html", context)


@login_required
@require_http_methods(["GET"])
def hashtag_groups_list_view(request):
    """Returns only the list of hashtag groups (used for HTMX dynamic updates)."""
    user = request.user
    hashtag_groups = TagGroup.objects.filter(user=user).prefetch_related("tags")
    return render(request, "postflow/components/hashtags_groups.html", {"hashtag_groups": hashtag_groups})


@require_http_methods(["GET"])
def privacy_policy(request):
    """Render the privacy policy page."""
    return render(request, "postflow/pages/privacy.html")

@require_http_methods(["POST"])
def subscribe(request):
    """Handle email subscription."""
    email = request.POST.get("email", "").strip()
    if not email:
        return JsonResponse({"error": "Email is required."}, status=400)
    subscriber, created = Subscriber.objects.get_or_create(email=email)
    if not created:
        return render(request, "postflow/components/partials/subscribe_already.html", {"email": email})
    return render(request, "postflow/components/partials/subscribe_success.html", {"email": email})


@login_required
@require_http_methods(["GET", "POST"])
def feedback_view(request):
    """Handle feedback submission and display feedback form."""
    from .models import Feedback

    success = False
    error_message = None

    if request.method == "POST":
        category = request.POST.get("category", "").strip()
        message = request.POST.get("message", "").strip()

        # Validation
        if not category or category not in ['improvement', 'bug', 'other']:
            error_message = "Please select a valid feedback category."
        elif not message or len(message) < 10:
            error_message = "Please provide feedback with at least 10 characters."
        else:
            # Save feedback
            try:
                Feedback.objects.create(
                    user=request.user,
                    category=category,
                    message=message
                )
                success = True
            except Exception as e:
                logger.error(f"Error saving feedback: {e}")
                error_message = "An error occurred while saving your feedback. Please try again."

    context = {
        'active_page': 'feedback',
        'success': success,
        'error_message': error_message,
    }

    if request.headers.get("HX-Request"):
        # Return both the content and sidebar with OOB swap
        sidebar_context = {**context, 'is_htmx_request': True}
        content = render(request, 'postflow/components/feedback.html', context).content.decode('utf-8')
        sidebar = render(request, 'postflow/components/sidebar_nav.html', sidebar_context).content.decode('utf-8')
        return HttpResponse(content + sidebar)

    return render(request, 'postflow/pages/feedback.html', context)


@login_required
@require_http_methods(["GET"])
def posted_history_view(request):
    """Display previously posted images with infinite scroll pagination."""

    # Get current month date range (1st of month to today)
    current_time = now()
    first_of_month = current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Pagination settings
    page = int(request.GET.get('page', 1))
    per_page = 25
    start = (page - 1) * per_page
    end = start + per_page

    # Query posted posts in reverse chronological order
    all_posted_posts = ScheduledPost.objects.filter(
        user=request.user,
        status='posted',
        post_date__lte=current_time
    ).prefetch_related(
        'images',
        'hashtag_groups__tags',
        'mastodon_accounts',
        'mastodon_native_accounts',
        'instagram_accounts'
    ).order_by('-post_date')

    # Get total count for pagination
    total_count = all_posted_posts.count()

    # Get paginated slice
    posted_posts = all_posted_posts[start:end]

    # Generate signed URLs for images
    for post in posted_posts:
        # Handle multiple images via PostImage model
        if post.images.exists():
            post.image_urls = [get_s3_signed_url(img.image.name) for img in post.images.all()]
        # Fallback to legacy single image field
        elif post.image:
            post.image_urls = [get_s3_signed_url(post.image.name)]
        else:
            post.image_urls = []

        post.hashtags = list(Tag.objects.filter(tag_groups__in=post.hashtag_groups.all()).distinct())

    # Group posts by date
    grouped_posts = defaultdict(list)
    for post in posted_posts:
        grouped_posts[post.post_date.date()].append(post)

    # Check if there are more posts to load
    has_more = end < total_count
    next_page = page + 1 if has_more else None

    context = {
        'grouped_posts': dict(grouped_posts),
        'page': page,
        'has_more': has_more,
        'next_page': next_page,
        'total_count': total_count,
    }

    # Handle HTMX requests
    if "HX-Request" in request.headers:
        # If it's page > 1, return only the posts (for infinite scroll)
        if page > 1:
            return render(request, "postflow/components/posted_history_items.html", context)
        # If it's page 1 HTMX (toggle button), return full component
        return render(request, "postflow/components/posted_history.html", context)

    # Regular page load (full page)
    return render(request, "postflow/pages/calendar.html", context)
