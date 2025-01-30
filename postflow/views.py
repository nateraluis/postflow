from django.db import IntegrityError
from django_htmx.http import retarget, reswap
from django.shortcuts import render
from django.shortcuts import redirect, reverse
from django.contrib.auth import authenticate, login
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import CustomUserCreationForm, CustomAuthenticationForm, HashtagCreationForm
from .models import Tag


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
    return render(request, "postflow/profile.html", context)

@login_required
@require_http_methods(["GET"])
def dashboard(request):
    return render(request, 'postflow/components/dashboard.html')


@login_required
@require_http_methods(["GET", "POST"])
def hashtags_view(request):
    if request.method == "POST":
        form = HashtagCreationForm(request.POST)
        if form.is_valid():
            try:
                hashtag = form.cleaned_data["hashtag"]
                Tag.objects.create(
                    name=hashtag,
                    user=request.user   
                )
                if request.headers.get("HX-Request"):
                    return HttpResponse(f"""
                    <tr>
                      <td class="py-4 pr-3 pl-4 text-sm font-medium whitespace-nowrap text-gray-900 sm:pl-0">
                        {hashtag}
                      </td>
                    </tr>
                    """)
                
                return redirect("add-hashtag")

            except IntegrityError:
                if request.headers.get("HX-Request"):
                    form.add_error("hashtag", "Hashtag already exists!")
                    hashtags = Tag.objects.all()
                    context = {"form": form, "hashtags": hashtags}
                    return reswap(retarget(render(request, 'postflow/components/hashtags.html', context), "#content-area"), "innerHTML")
                else:
                    form.add_error("hashtag", "Hashtag already exists!")
    else:
        form = HashtagCreationForm()
    hashtags = Tag.objects.all()
    context = {"form": form, "hashtags": hashtags}
    return render(request, 'postflow/components/hashtags.html', context)


@login_required
@require_http_methods(["GET"])
def calendar_view(request):
    return render(request, 'postflow/components/calendar.html')

@login_required
@require_http_methods(["POST"])
def add_hashtag_view(request):
    pass
