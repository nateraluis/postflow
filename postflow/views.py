from django.db import IntegrityError
import requests
from django.shortcuts import render
from django.shortcuts import redirect, reverse, get_object_or_404
from django.contrib.auth import authenticate, login
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .forms import CustomUserCreationForm, CustomAuthenticationForm 
from .models import Tag, TagGroup, MastodonAccount
import os

REDIRECT_URI = 'https://postflow.photo/mastodon/callback'

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
            form.save()
            username = form.cleaned_data["email"]
            user = authenticate(
                username=username,
                password=form.cleaned_data["password1"],
            )
            login(request, user)
            return redirect("profile", username=username)
        else:
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
    return render(request, 'postflow/components/calendar.html')


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



@login_required
@require_http_methods(["GET", "POST"])
def connect_mastodon(request):
    if request.method == "POST":
        instance_url = request.POST.get("instance_url").strip().rstrip("/")
        if not instance_url.startswith("https://"):
            instance_url = f"https://{instance_url}"

        # Step 1: Register the app with Mastodon
        response = requests.post(f"{instance_url}/api/v1/apps", data={
            "client_name": "Your App Name",
            "redirect_uris": REDIRECT_URI,
            "scopes": "read write",
            "website": "https://yourwebsite.com"
        })

        if response.status_code == 200:
            app_data = response.json()
            request.session["mastodon_instance"] = instance_url
            request.session["mastodon_client_id"] = app_data["client_id"]
            request.session["mastodon_client_secret"] = app_data["client_secret"]

            # Step 2: Redirect user to Mastodon authorization page
            auth_url = (
                f"{instance_url}/oauth/authorize"
                f"?client_id={app_data['client_id']}"
                f"&scope=read+write"
                f"&redirect_uri={REDIRECT_URI}"
                f"&response_type=code"
            )
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
    REDIRECT_URI = request.build_absolute_uri("/mastodon/callback/")
    
    # Step 3: Exchange code for access token
    token_response = requests.post(f"{instance_url}/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code
    })

    if token_response.status_code == 200:
        token_data = token_response.json()
        access_token = token_data["access_token"]
        print(access_token)

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
