"""Weekly campaign evaluation: deterministic context assembly + one Claude call.

The model only sees figures computed here; the prompt requires it to cite only
provided numbers. Recommendations are rendered in the UI as suggestions, never
auto-scheduled.
"""
import json
import logging
from datetime import timedelta
from typing import List, Literal, Optional

import anthropic
from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel, Field

from postflow.models import FollowerSnapshot, ScheduledPost

from .models import CampaignReport
from .planner import pick_evergreen

logger = logging.getLogger("postflow")

EVALUATOR_PROMPT_VERSION = "v1"


class Recommendation(BaseModel):
    type: Literal["promote_new", "evergreen", "timing", "other"]
    platform: str = Field(description="Target platform, or 'all'")
    blog_post_id: Optional[int] = Field(
        default=None, description="websites.BlogPost id this recommendation refers to, if any"
    )
    rationale: str


class ReportOutput(BaseModel):
    report_markdown: str = Field(
        description="The weekly report in markdown, citing only figures from the provided data"
    )
    recommendations: List[Recommendation]


def generate_report(user, website=None, week_start=None):
    """Create (or replace) the weekly CampaignReport for the given week."""
    if website is None:
        website = user.websites.first()
    today = timezone.now().date()
    if week_start is None:
        # Monday of the current week: a mid-week manual run and the following
        # Monday cron run land on different weeks, and re-runs within the same
        # week update the same report (trailing 7-day data window either way).
        week_start = today - timedelta(days=today.weekday())

    context = _build_context(user, website)

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)
    response = client.messages.parse(
        model=settings.ANTHROPIC_MODEL_ANALYSIS,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=_system_prompt(user),
        messages=[{
            "role": "user",
            "content": (
                "Here is this week's campaign data as JSON. Write the weekly report "
                "and recommendations.\n\n" + json.dumps(context, default=str)
            ),
        }],
        output_format=ReportOutput,
    )
    output = response.parsed_output
    if output is None:
        raise RuntimeError("Campaign evaluation returned no parseable output")

    report, _ = CampaignReport.objects.update_or_create(
        user=user,
        website=website,
        week_start=week_start,
        defaults={
            "report_markdown": output.report_markdown,
            "recommendations": [r.model_dump() for r in output.recommendations],
            "model_used": settings.ANTHROPIC_MODEL_ANALYSIS,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )
    return report


def _system_prompt(user):
    from .ai import get_voice_profile

    voice = get_voice_profile(user)
    return (
        "You are the analyst for a personal social media campaign whose goal is to "
        "grow website visitors and newsletter subscribers.\n"
        "Write a short weekly report (300 words maximum) about what worked, what did not, "
        "and what to do next week.\n"
        "Cite ONLY numbers that appear in the provided data. Never invent or extrapolate "
        "figures. If data is missing, say so plainly.\n"
        "Recommendations must be specific and actionable (which post, which platform, why).\n\n"
        "Write the report following these voice rules:\n"
        f"{voice.rules}"
    )


def _build_context(user, website):
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    context = {
        "website": website.url if website else None,
        "period": {"from": week_ago.date(), "to": now.date()},
    }

    # Site analytics (visitors/subscribers), if the analytics_site app has data
    try:
        from analytics_site import utils as site_utils

        if website:
            series = site_utils.get_series(website, days=14)
            context["site_daily"] = series
            context["signups_by_source"] = site_utils.get_signups_by_source(website, days=14)
            context["utm_sources"] = site_utils.get_utm_sources(website, days=14)
            context["post_impact"] = [
                {
                    "platform": row.get("platform"),
                    "post_date": row.get("post_date"),
                    "visitors_after": row.get("visitors_after"),
                    "baseline": row.get("baseline"),
                    "lift_pct": row.get("lift_pct"),
                }
                for row in site_utils.get_post_impact(user, website, days=14)
            ]
    except Exception:
        logger.exception("Site analytics unavailable for campaign report")
        context["site_daily"] = "unavailable"

    # Social engagement
    try:
        from analytics.utils import get_top_performers

        top = get_top_performers(user, days=7, limit=5)
        context["top_social_posts"] = top.get("posts", top) if isinstance(top, dict) else top
    except Exception:
        logger.exception("Social analytics unavailable for campaign report")

    # Follower growth deltas per platform over the week
    followers = {}
    for snap in FollowerSnapshot.objects.filter(user=user, date__gte=two_weeks_ago.date()):
        key = f"{snap.platform}:{snap.account_username}"
        followers.setdefault(key, []).append(
            {"date": str(snap.date), "followers": snap.followers_count}
        )
    context["follower_snapshots"] = followers

    # What was posted this week
    posted = ScheduledPost.objects.filter(
        user=user, status="posted", post_date__gte=week_ago
    ).prefetch_related("generated_draft")
    context["posted_this_week"] = [
        {
            "post_date": p.post_date,
            "caption_excerpt": (p.caption or "")[:200],
            "ai_generated": hasattr(p, "generated_draft"),
            "platform": getattr(getattr(p, "generated_draft", None), "platform", "manual"),
        }
        for p in posted
    ]

    # Drafts still waiting for review
    context["drafts_waiting"] = ScheduledPost.objects.filter(
        user=user, status="draft", generated_draft__isnull=False
    ).count()

    # Evergreen candidate
    if website:
        candidate = pick_evergreen(website)
        if candidate:
            context["evergreen_candidate"] = {
                "blog_post_id": candidate.id,
                "title": candidate.title,
                "published_at": candidate.published_at,
                "promo_count": candidate.promo_count,
                "last_promoted_at": candidate.last_promoted_at,
            }

    return context
