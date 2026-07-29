import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from postflow.models import ScheduledPost
from websites.models import BlogPost

from . import ai, planner
from .models import Campaign, GeneratedDraft

logger = logging.getLogger("postflow")

PLATFORM_CHOICES = ["instagram", "pixelfed", "mastodon", "linkedin", "threads", "glass"]


@login_required
def promote_form(request, blog_post_id):
    blog_post = get_object_or_404(BlogPost, pk=blog_post_id, website__user=request.user)
    slots = planner.propose_slots(request.user, count=3)
    return render(request, "campaigns/promote.html", {
        "blog_post": blog_post,
        "platforms": PLATFORM_CHOICES,
        "slots": slots,
        "active_page": "websites",
    })


@login_required
@require_POST
def promote(request, blog_post_id):
    blog_post = get_object_or_404(BlogPost, pk=blog_post_id, website__user=request.user)
    platforms = [p for p in request.POST.getlist("platforms") if p in PLATFORM_CHOICES]
    if not platforms:
        messages.error(request, "Pick at least one platform.")
        return redirect("campaigns:promote_form", blog_post.id)

    goal = request.POST.get("goal", "new_issue")
    campaign = Campaign.objects.create(
        user=request.user,
        website=blog_post.website,
        blog_post=blog_post,
        name=f"Promote: {blog_post.title}"[:255],
        goal=goal if goal in dict(Campaign.GOAL_CHOICES) else "new_issue",
        utm_campaign=slugify(f"{blog_post.slug or blog_post.id}-{timezone.now():%Y%m%d}")[:100],
    )

    slots = planner.propose_slots(request.user, count=len(platforms))
    try:
        results = ai.generate_drafts(campaign, platforms, slots)
    except Exception:
        logger.exception(f"Draft generation failed for campaign {campaign.id}")
        campaign.delete()
        messages.error(request, "Draft generation failed. Check the Claude API key and try again.")
        return redirect("websites:detail", blog_post.website.id)

    messages.success(
        request,
        f"{len(results)} draft(s) generated. Review and approve them before they post.",
    )
    return redirect("campaigns:queue")


@login_required
def review_queue(request):
    drafts = (
        GeneratedDraft.objects.filter(
            campaign__user=request.user, scheduled_post__status="draft"
        )
        .select_related("scheduled_post", "campaign", "campaign__blog_post")
        .prefetch_related("scheduled_post__images")
        .order_by("scheduled_post__post_date")
    )
    reports = request.user.campaign_reports.all()[:5]
    return render(request, "campaigns/queue.html", {
        "drafts": drafts,
        "reports": reports,
        "active_page": "campaigns",
    })


@login_required
@require_POST
def approve_draft(request, pk):
    draft = get_object_or_404(GeneratedDraft, pk=pk, campaign__user=request.user)
    post = draft.scheduled_post

    if not _has_delivery_target(post):
        messages.error(
            request,
            f"This {draft.platform} draft has no connected account to post to. "
            "Connect the account (or set your posting defaults) first.",
        )
        return redirect("campaigns:queue")

    caption = request.POST.get("caption")
    if caption is not None and caption.strip():
        post.caption = caption

    from postflow.payload import build_payload

    errors = build_payload(post).validate_for_platform(draft.platform)
    if errors:
        post.save(update_fields=["caption"])  # keep the edit, stay in draft
        messages.error(request, f"Fix before approving: {'; '.join(errors)}")
        return redirect("campaigns:queue")

    post.status = "pending"
    post.save()

    campaign = draft.campaign
    if campaign.status == "draft":
        campaign.status = "active"
        campaign.save(update_fields=["status"])
        if campaign.blog_post:
            ai.mark_promoted(campaign.blog_post)

    messages.success(request, "Draft approved. It will post at the scheduled time.")
    return redirect("campaigns:queue")


@login_required
@require_POST
def discard_draft(request, pk):
    draft = get_object_or_404(GeneratedDraft, pk=pk, campaign__user=request.user)
    draft.scheduled_post.delete()
    messages.success(request, "Draft discarded.")
    return redirect("campaigns:queue")


@login_required
@require_POST
def regenerate_draft(request, pk):
    draft = get_object_or_404(GeneratedDraft, pk=pk, campaign__user=request.user)
    campaign = draft.campaign
    platform = draft.platform
    post_date = draft.scheduled_post.post_date

    try:
        # Generate the replacement first so a failed API call keeps the old draft
        ai.generate_drafts(campaign, [platform], [post_date])
    except Exception:
        logger.exception(f"Regeneration failed for campaign {campaign.id}")
        messages.error(request, "Regeneration failed. The previous draft was kept.")
        return redirect("campaigns:queue")

    draft.scheduled_post.delete()
    messages.success(request, f"New {platform} draft generated.")
    return redirect("campaigns:queue")


@login_required
@require_POST
def run_autopilot_now(request):
    from . import autopilot

    try:
        summary, results = autopilot.run_autopilot(request.user)
        messages.success(
            request, f"Autopilot planned {len(results)} draft(s) for review. {summary}"
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception:
        logger.exception("Autopilot failed")
        messages.error(request, "Autopilot failed. Check the Claude API key and try again.")
    return redirect("campaigns:queue")


@login_required
def report_list(request):
    reports = request.user.campaign_reports.all()
    return render(request, "campaigns/reports.html", {
        "reports": reports,
        "active_page": "campaigns",
    })


@login_required
def report_detail(request, pk):
    report = get_object_or_404(request.user.campaign_reports, pk=pk)
    recommendations = []
    for rec in report.recommendations:
        blog_post = None
        if rec.get("blog_post_id"):
            blog_post = BlogPost.objects.filter(
                pk=rec["blog_post_id"], website__user=request.user
            ).first()
        recommendations.append({**rec, "blog_post": blog_post})
    return render(request, "campaigns/report_detail.html", {
        "report": report,
        "recommendations": recommendations,
        "active_page": "campaigns",
    })


@login_required
@require_POST
def generate_report_now(request):
    from . import evaluator

    try:
        report = evaluator.generate_report(request.user)
        messages.success(request, f"Report for the week of {report.week_start} generated.")
        return redirect("campaigns:report_detail", report.pk)
    except Exception:
        logger.exception("Manual report generation failed")
        messages.error(request, "Report generation failed. Check the Claude API key.")
        return redirect("campaigns:reports")


def _has_delivery_target(post):
    """A post can only be approved if some connected account will deliver it."""
    return (
        post.mastodon_accounts.exists()
        or post.mastodon_native_accounts.exists()
        or post.instagram_accounts.exists()
        or post.linkedin_accounts.exists()
        or post.threads_accounts.exists()
        or post.glass_accounts.exists()
    )
