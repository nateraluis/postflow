import logging

import requests
from bs4 import BeautifulSoup
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AddWebsiteForm, ContentAPIKeyForm
from .models import BlogPost, ContentSource, Website
from .sources import build_adapter, detect_sources, make_session
from .sync import SyncError, sync_website

logger = logging.getLogger("postflow")


@login_required
def website_list(request):
    websites = request.user.websites.all().order_by("created_at")
    return render(request, "websites/list.html", {
        "websites": websites,
        "form": AddWebsiteForm(),
        "active_page": "websites",
    })


@login_required
@require_POST
def website_add(request):
    form = AddWebsiteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid website URL.")
        return redirect("websites:list")

    url = form.cleaned_data["url"]
    if request.user.websites.filter(url=url).exists():
        messages.info(request, "That website is already connected.")
        return redirect("websites:list")

    detected = detect_sources(url)
    if not detected:
        messages.error(
            request,
            "Could not find any content on that site (no Ghost API, RSS feed, or sitemap).",
        )
        return redirect("websites:list")

    website, created = Website.objects.get_or_create(
        user=request.user,
        url=url,
        defaults={
            "title": _fetch_site_title(url),
            "detected_platform": (
                "ghost" if any(k.startswith("ghost") for k, _, _ in detected) else "unknown"
            ),
        },
    )
    if not created:
        messages.info(request, "That website is already connected.")
        return redirect("websites:detail", website.id)
    for kind, config, priority in detected:
        ContentSource.objects.create(
            website=website,
            kind=kind,
            config=config,
            priority=priority,
            # The Content API needs a user-supplied key before it can be used
            is_active=(kind != "ghost_content_api" or bool(config.get("api_key"))),
        )

    sources = ", ".join(dict(ContentSource.KIND_CHOICES)[k] for k, _, _ in detected)
    messages.success(request, f"Website added. Detected sources: {sources}.")
    return redirect("websites:detail", website.id)


@login_required
def website_detail(request, pk):
    website = get_object_or_404(Website, pk=pk, user=request.user)
    posts = website.posts.prefetch_related("images")
    return render(request, "websites/detail.html", {
        "website": website,
        "posts": posts,
        "sources": website.sources.all(),
        "api_key_form": ContentAPIKeyForm(),
        "active_page": "websites",
    })


@login_required
@require_POST
def website_sync(request, pk):
    website = get_object_or_404(Website, pk=pk, user=request.user)
    try:
        created, updated = sync_website(website)
        messages.success(request, f"Sync complete: {created} new, {updated} updated.")
    except SyncError as e:
        messages.error(request, str(e))
    except Exception:
        logger.exception(f"Sync failed for {website.url}")
        messages.error(request, "Sync failed. Check the source configuration.")
    return redirect("websites:detail", website.id)


@login_required
@require_POST
def website_add_api_key(request, pk):
    website = get_object_or_404(Website, pk=pk, user=request.user)
    form = ContentAPIKeyForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter an API key.")
        return redirect("websites:detail", website.id)

    source = website.sources.filter(kind="ghost_content_api").first()
    if source is None:
        messages.error(request, "This website has no Ghost Content API source.")
        return redirect("websites:detail", website.id)

    source.config["api_key"] = form.cleaned_data["api_key"].strip()
    if _api_key_works(source):
        source.is_active = True
        source.save(update_fields=["config", "is_active"])
        messages.success(request, "API key verified. Future syncs will use the Ghost Content API.")
    else:
        messages.error(request, "That API key did not work against the Ghost Content API.")
    return redirect("websites:detail", website.id)


@login_required
@require_POST
def website_delete(request, pk):
    website = get_object_or_404(Website, pk=pk, user=request.user)
    website.delete()
    messages.success(request, "Website removed.")
    return redirect("websites:list")


def _api_key_works(source):
    try:
        next(iter(build_adapter(source).fetch_posts()))
        return True
    except StopIteration:
        return True  # Valid key, site just has no posts
    except Exception:
        logger.exception("Ghost Content API key validation failed")
        return False


def _fetch_site_title(url):
    try:
        resp = make_session().get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            return og["content"][:255]
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:255]
    except requests.RequestException:
        pass
    return ""
