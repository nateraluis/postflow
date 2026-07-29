"""AI drafting service: turn a BlogPost into platform-specific ScheduledPost drafts.

Drafts are created with status="draft" — the existing scheduler only publishes
"pending" posts, so nothing generated here can post without explicit approval.
"""
import logging
from pathlib import Path
from typing import List, Literal

import anthropic
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, Field

from postflow.models import PostImage, ScheduledPost, UserDefaults
from postflow.payload import build_payload

from .models import GeneratedDraft, VoiceProfile
from .utm import tag_url

logger = logging.getLogger("postflow")

PROMPT_VERSION = "v1"
DEFAULT_VOICE_PATH = Path(__file__).parent / "voice" / "default.md"

Platform = Literal["instagram", "pixelfed", "mastodon", "linkedin", "threads", "glass"]

PLATFORM_CAPTION_LIMITS = {
    "instagram": 2200,
    "pixelfed": 500,
    "mastodon": 500,
    "linkedin": 3000,
    "threads": 500,
    "glass": 600,
}


class PlatformDraft(BaseModel):
    platform: Platform
    caption: str = Field(description="Full post caption, ready to publish, without hashtags")
    hashtags: List[str] = Field(description="Hashtags without the # prefix")
    image_indices: List[int] = Field(
        description="Indices into the provided image list, best image first"
    )


class DraftBatch(BaseModel):
    drafts: List[PlatformDraft]


def get_voice_profile(user):
    """Return the user's default voice profile, seeding it from the packaged
    default rules on first use."""
    profile = (
        VoiceProfile.objects.filter(user=user, is_default=True).first()
        or VoiceProfile.objects.filter(user=user).first()
    )
    if profile is None:
        profile = VoiceProfile.objects.create(
            user=user,
            name="Default",
            is_default=True,
            rules=DEFAULT_VOICE_PATH.read_text(),
        )
    return profile


def generate_drafts(campaign, platforms, slots):
    """Generate one ScheduledPost draft per requested platform.

    Returns a list of (ScheduledPost, GeneratedDraft) tuples.
    """
    blog_post = campaign.blog_post
    if blog_post is None:
        raise ValueError("Campaign has no blog post to promote")

    user = campaign.user
    voice = get_voice_profile(user)
    images = list(blog_post.images.exclude(image=""))

    # Falls back to ANTHROPIC_API_KEY env / ant auth profile when unset in Django settings
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)
    response = client.messages.parse(
        model=settings.ANTHROPIC_MODEL_DRAFTING,
        max_tokens=8000,
        system=_system_prompt(voice),
        messages=[{
            "role": "user",
            "content": _draft_request(blog_post, campaign, platforms, images),
        }],
        output_format=DraftBatch,
    )
    batch = response.parsed_output
    if batch is None:
        raise RuntimeError("Draft generation returned no parseable output")

    # One draft per requested platform, deterministic slot pairing
    drafts_by_platform = {}
    for draft in batch.drafts:
        if draft.platform in platforms and draft.platform not in drafts_by_platform:
            drafts_by_platform[draft.platform] = draft

    created = [p for p in platforms if p in drafts_by_platform]
    per_draft_input = response.usage.input_tokens // max(len(created), 1)
    per_draft_output = response.usage.output_tokens // max(len(created), 1)

    results = []
    with transaction.atomic():
        for i, platform in enumerate(created):
            draft = drafts_by_platform[platform]
            post_date = (
                slots[i] if i < len(slots) else timezone.now() + timezone.timedelta(hours=6)
            )
            post = _create_scheduled_post(user, draft, post_date, images)
            generated = GeneratedDraft.objects.create(
                campaign=campaign,
                scheduled_post=post,
                platform=platform,
                model_used=settings.ANTHROPIC_MODEL_DRAFTING,
                prompt_version=PROMPT_VERSION,
                input_tokens=per_draft_input,
                output_tokens=per_draft_output,
            )
            errors = build_payload(post).validate_for_platform(platform)
            if errors:
                logger.warning(f"Draft for {platform} has validation issues: {errors}")
            results.append((post, generated))

    return results


def mark_promoted(blog_post):
    blog_post.last_promoted_at = timezone.now()
    blog_post.promo_count += 1
    blog_post.save(update_fields=["last_promoted_at", "promo_count"])


def _system_prompt(voice):
    return (
        "You turn blog posts into social media drafts for the blog's author. "
        "You write as the author, in their voice, following their rules exactly.\n\n"
        f"{voice.rules}"
    )


def _draft_request(blog_post, campaign, platforms, images):
    image_lines = [
        f"{i}: {img.alt_text or '(no alt text)'}{' [feature image]' if img.is_feature else ''}"
        for i, img in enumerate(images)
    ] or ["(no images available)"]

    platform_lines = []
    for platform in platforms:
        url = tag_url(blog_post.url, platform, campaign.utm_campaign)
        limit = PLATFORM_CAPTION_LIMITS[platform]
        platform_lines.append(
            f"- {platform}: caption + hashtags must stay under {limit} characters. "
            f"Link to include (except on instagram and glass, which do not support links): {url}"
        )

    body = blog_post.body_for_ai[:12000]
    return f"""Create one social media draft for each of these platforms:
{chr(10).join(platform_lines)}

Rules for every draft:
- Reuse the author's own sentences from the post verbatim wherever possible.
- Pick 1-4 of the available images by index (glass and instagram need at least one image if any exist).
- Do not include hashtags inside the caption text; list them separately.
- On instagram, mention that the link is in the bio instead of pasting a URL.

Blog post title: {blog_post.title}

Blog post content:
{body}

Available images:
{chr(10).join(image_lines)}
"""


def _create_scheduled_post(user, draft, post_date, images):
    caption = _apply_hard_rules(draft.caption)
    hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in draft.hashtags)
    if hashtag_str:
        caption = f"{caption}\n\n{hashtag_str}"

    post = ScheduledPost.objects.create(
        user=user,
        caption=caption,
        post_date=post_date,
        status="draft",
    )

    _assign_default_accounts(post, draft.platform)

    order = 0
    for index in dict.fromkeys(draft.image_indices):
        if 0 <= index < len(images):
            source = images[index]
            # Reference the already-stored file; no second copy is uploaded
            PostImage.objects.create(
                scheduled_post=post,
                image=source.image.name,
                alt_text=source.alt_text,
                order=order,
            )
            order += 1
    return post


def _assign_default_accounts(post, platform):
    defaults = UserDefaults.objects.filter(user=post.user).first()
    if defaults is None:
        return
    if platform == "pixelfed":
        post.mastodon_accounts.set(defaults.default_mastodon_accounts.all())
    elif platform == "mastodon":
        post.mastodon_native_accounts.set(defaults.default_mastodon_native_accounts.all())
    elif platform == "instagram":
        post.instagram_accounts.set(defaults.default_instagram_accounts.all())
    elif platform == "linkedin":
        accounts = defaults.default_linkedin_accounts.all()
        if not accounts:
            accounts = post.user.linkedin_accounts.all()
        post.linkedin_accounts.set(accounts)
    elif platform == "threads":
        accounts = defaults.default_threads_accounts.all()
        if not accounts:
            accounts = post.user.threads_accounts.all()
        post.threads_accounts.set(accounts)
    elif platform == "glass":
        accounts = defaults.default_glass_accounts.all()
        if not accounts:
            accounts = post.user.glass_accounts.all()
        post.glass_accounts.set(accounts)


def _apply_hard_rules(text):
    """Cheap enforcement of the non-negotiable voice rules."""
    return text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").replace("–", ", ")
