"""Campaign autopilot: turn collected data into a scheduled week of drafts.

Pipeline (data is already collected by scheduler jobs):
  website content  -> websites app (sync_website_content)
  social metrics   -> analytics_* apps (hourly sync jobs)
  site analytics   -> analytics_site app (collect_site_analytics / import)
This module assembles that data, asks Claude to identify opportunities and plan
the coming days, then generates platform drafts for each planned item.

Everything lands as status="draft" in the review queue: the user approves,
edits, or rejects. The autopilot never publishes anything.
"""
import json
import logging
from datetime import timedelta
from typing import List, Literal, Optional

import anthropic
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from pydantic import BaseModel, Field

from postflow.models import ScheduledPost

from . import ai, planner
from .models import Campaign, GeneratedDraft

logger = logging.getLogger("postflow")

MAX_PLANNED_POSTS = 5
RECENT_PROMO_DAYS = 21

Platform = Literal["instagram", "pixelfed", "mastodon", "linkedin", "threads", "glass"]


class PlannedItem(BaseModel):
    blog_post_id: int = Field(description="id from the available content list")
    platforms: List[Platform]
    goal: Literal["new_issue", "evergreen"]
    rationale: str = Field(
        description="One or two plain sentences: why this post, these platforms, now"
    )


class WeeklyPlan(BaseModel):
    plan_summary: str = Field(description="Two or three sentences describing the week's plan")
    items: List[PlannedItem]


def run_autopilot(user, website=None, max_posts=MAX_PLANNED_POSTS):
    """Plan the coming week and generate drafts for review.

    Returns (plan_summary, [(ScheduledPost, GeneratedDraft), ...]).
    """
    website = website or user.websites.first()
    if website is None:
        raise ValueError("No website connected")

    connected = connected_platforms(user)
    if not connected:
        raise ValueError("No social accounts connected")

    context = _build_context(user, website, connected, max_posts)

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)
    response = client.messages.parse(
        model=settings.ANTHROPIC_MODEL_ANALYSIS,
        max_tokens=6000,
        thinking={"type": "adaptive"},
        system=_system_prompt(max_posts),
        messages=[{
            "role": "user",
            "content": (
                "Here is the current data as JSON. Plan the coming week.\n\n"
                + json.dumps(context, default=str)
            ),
        }],
        output_format=WeeklyPlan,
    )
    plan = response.parsed_output
    if plan is None:
        raise RuntimeError("Autopilot returned no parseable plan")

    results = _execute_plan(user, website, plan, connected, max_posts)
    logger.info(
        f"Autopilot planned {len(results)} draft(s) for {user.email}: {plan.plan_summary}"
    )
    return plan.plan_summary, results


def connected_platforms(user):
    # Mirrors how drafts are delivered: "pixelfed" posts go to the
    # pixelfed/Mastodon-compatible accounts, "mastodon" to native Mastodon.
    checks = {
        "pixelfed": user.mastodon_accounts.exists(),
        "mastodon": user.mastodon_native_accounts.exists(),
        "instagram": user.instagram_business_accounts.exists(),
        "linkedin": user.linkedin_accounts.exists(),
        "threads": user.threads_accounts.exists(),
        "glass": user.glass_accounts.exists(),
    }
    return sorted(p for p, ok in checks.items() if ok)


def _system_prompt(max_posts):
    return (
        "You are the campaign planner for a personal blog whose goal is to grow "
        "website visitors and newsletter subscribers through social media.\n"
        f"Plan at most {max_posts} posts for the coming 7 days.\n"
        "How to plan:\n"
        "- Look for opportunities in the data: content that matches what people "
        "already search for (search queries), pages that already attract visitors, "
        "platforms that historically drive visits or signups, fresh content that "
        "has never been promoted, and strong archive posts that are due again.\n"
        "- Only use platforms from the connected list.\n"
        "- Spread posts across the week and across platforms; do not plan the same "
        "blog post twice.\n"
        "- Skip anything in the recently-promoted list unless there is a clear "
        "reason (say the reason in the rationale).\n"
        "- Each rationale must reference the data plainly (no invented numbers).\n"
        "Quality over quantity: fewer good posts beat a full calendar."
    )


def _build_context(user, website, connected, max_posts):
    now = timezone.now()
    recent_cutoff = now - timedelta(days=RECENT_PROMO_DAYS)

    posts = website.posts.all()
    fresh = [
        _post_line(p)
        for p in posts.filter(last_promoted_at__isnull=True).order_by("-published_at")[:8]
    ]
    evergreen = [
        _post_line(p)
        for p in posts.filter(
            last_promoted_at__isnull=False, last_promoted_at__lt=recent_cutoff
        ).order_by("last_promoted_at")[:8]
    ]
    recently_promoted = [
        _post_line(p)
        for p in posts.filter(last_promoted_at__gte=recent_cutoff).order_by(
            "-last_promoted_at"
        )[:10]
    ]

    context = {
        "today": now.date(),
        "connected_platforms": connected,
        "max_posts": max_posts,
        "available_content": {
            "never_promoted": fresh,
            "evergreen_candidates": evergreen,
        },
        "recently_promoted_avoid": recently_promoted,
        "drafts_already_waiting_review": ScheduledPost.objects.filter(
            user=user, status="draft", generated_draft__isnull=False
        ).count(),
    }

    try:
        from analytics_site import utils as site_utils
        from analytics_site.models import SiteSnapshot

        context["site_last_14_days"] = site_utils.get_series(website, days=14)
        context["signups_by_source_30d"] = site_utils.get_signups_by_source(website, days=30)
        context["utm_sources_30d"] = site_utils.get_utm_sources(website, days=30)
        context["post_impact_30d"] = site_utils.get_post_impact(user, website, days=30)

        seo = site_utils.get_seo_overview(website, days=28)
        if seo and seo.get("has_data"):
            context["seo"] = {
                "totals_28d": seo["totals"],
                "top_queries": seo["top_queries"],
                "top_pages_in_search": seo["top_pages"],
                "striking_distance_queries": seo["opportunities"],
            }
        latest_p = SiteSnapshot.objects.filter(website=website).exclude(plausible={}).first()
        if latest_p:
            context["top_pages"] = ((latest_p.plausible or {}).get("pages") or [])[:10]
    except Exception:
        logger.exception("Site analytics unavailable for autopilot")

    try:
        from analytics.utils import get_best_posting_times, get_top_performers

        top = get_top_performers(user, days=30, limit=5)
        context["top_social_posts_30d"] = top.get("posts", top) if isinstance(top, dict) else top
        context["best_posting_times"] = get_best_posting_times(user).get("suggestions", [])
    except Exception:
        logger.exception("Social analytics unavailable for autopilot")

    return context


def _post_line(post):
    return {
        "blog_post_id": post.id,
        "title": post.title,
        "url": post.url,
        "tags": post.tags,
        "published_at": post.published_at,
        "promo_count": post.promo_count,
        "last_promoted_at": post.last_promoted_at,
    }


def _execute_plan(user, website, plan, connected, max_posts):
    results = []
    seen_posts = set()

    # One slot per (item, platform), spread over the coming week
    total_needed = sum(
        len([p for p in item.platforms if p in connected]) for item in plan.items[:max_posts]
    )
    slots = planner.propose_slots(user, count=max(total_needed, 1), horizon_days=7)
    slot_iter = iter(slots)

    for item in plan.items[:max_posts]:
        if item.blog_post_id in seen_posts:
            continue
        blog_post = website.posts.filter(id=item.blog_post_id).first()
        if blog_post is None:
            logger.warning(f"Autopilot planned unknown blog post id {item.blog_post_id}")
            continue
        platforms = [p for p in dict.fromkeys(item.platforms) if p in connected]
        if not platforms:
            continue
        seen_posts.add(item.blog_post_id)

        campaign = Campaign.objects.create(
            user=user,
            website=website,
            blog_post=blog_post,
            name=f"Autopilot: {blog_post.title}"[:255],
            goal=item.goal,
            rationale=item.rationale,
            utm_campaign=slugify(
                f"{blog_post.slug or blog_post.id}-{timezone.now():%Y%m%d}"
            )[:100],
        )
        item_slots = [
            next(slot_iter, timezone.now() + timedelta(days=2)) for _ in platforms
        ]
        try:
            results.extend(ai.generate_drafts(campaign, platforms, item_slots))
        except Exception:
            logger.exception(f"Autopilot draft generation failed for {blog_post.title}")
            campaign.delete()

    return results
