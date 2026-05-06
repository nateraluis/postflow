"""
PostPayload: centralized post context for cross-platform publishing.

Each platform publishing util receives a PostPayload instead of
reaching into ScheduledPost relations directly. This prevents
duplicating hashtag assembly, caption building, and validation
across platform utils.
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger("postflow")

# Platform-specific limits
INSTAGRAM_HASHTAG_LIMIT = 5
INSTAGRAM_CAPTION_LIMIT = 2200
MASTODON_CAPTION_LIMIT = 500


@dataclass
class PostPayload:
    """Assembled post context ready for platform publishing."""
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    pinned_hashtags: list[str] = field(default_factory=list)
    image_files: list = field(default_factory=list)
    alt_texts: list[str] = field(default_factory=list)
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    user_tags: list[dict] = field(default_factory=list)
    collaborators: list[str] = field(default_factory=list)
    spoiler_text: str = ""
    visibility: str = "public"
    language: str = ""
    sensitive: bool = False
    poll_options: list[str] = field(default_factory=list)
    poll_expires_in: Optional[int] = None
    poll_multiple: bool = False
    poll_hide_totals: bool = False

    def get_hashtag_string(self, platform: str = "default") -> str:
        """Get formatted hashtag string respecting platform limits and filtering banned tags."""
        from .hashtag_utils import select_hashtags_for_platform
        selected = select_hashtags_for_platform(
            self.hashtags, self.pinned_hashtags, platform
        )
        return " ".join(f"#{t}" for t in selected)

    def get_full_caption(self, platform: str = "default") -> str:
        """Get caption + hashtags assembled for a specific platform."""
        hashtag_str = self.get_hashtag_string(platform)
        parts = [p for p in [self.caption, hashtag_str] if p]
        return "\n".join(parts)

    def get_alt_text(self, index: int) -> str:
        """Get alt text for image at given index, or empty string."""
        if index < len(self.alt_texts):
            return self.alt_texts[index]
        return ""

    def validate_for_platform(self, platform: str) -> list[str]:
        """Validate payload for a specific platform. Returns list of error messages."""
        errors = []
        full_caption = self.get_full_caption(platform)

        if platform == "instagram":
            if len(full_caption) > INSTAGRAM_CAPTION_LIMIT:
                errors.append(
                    f"Caption exceeds Instagram limit ({len(full_caption)}/{INSTAGRAM_CAPTION_LIMIT} chars)"
                )
            hashtag_count = len(self.get_hashtag_string(platform).split()) if self.hashtags or self.pinned_hashtags else 0
            if hashtag_count > INSTAGRAM_HASHTAG_LIMIT:
                errors.append(
                    f"Too many hashtags for Instagram ({hashtag_count}/{INSTAGRAM_HASHTAG_LIMIT})"
                )
        elif platform in ("mastodon", "pixelfed"):
            if len(full_caption) > MASTODON_CAPTION_LIMIT:
                errors.append(
                    f"Caption exceeds {platform.title()} limit ({len(full_caption)}/{MASTODON_CAPTION_LIMIT} chars)"
                )

        return errors


def build_payload(scheduled_post) -> PostPayload:
    """
    Build a PostPayload from a ScheduledPost instance.
    Centralizes all the data gathering that was previously duplicated
    across platform utils.
    """
    # Collect hashtags
    all_hashtags = []
    pinned = []
    for tag_group in scheduled_post.hashtag_groups.all():
        for tag in tag_group.tags.all():
            if tag.name not in all_hashtags:
                all_hashtags.append(tag.name)
            if tag.pinned and tag.name not in pinned:
                pinned.append(tag.name)

    # Collect alt texts
    alt_texts = []
    if hasattr(scheduled_post, 'images') and scheduled_post.images.exists():
        for img in scheduled_post.images.all():
            alt_texts.append(getattr(img, 'alt_text', '') or '')

    # Collect user tags
    user_tags = []
    if hasattr(scheduled_post, 'user_tags'):
        for ut in scheduled_post.user_tags.all():
            user_tags.append({
                'username': ut.username,
                'platform': ut.platform,
                'x': ut.x,
                'y': ut.y,
            })

    # Collect collaborators
    collaborators = []
    if hasattr(scheduled_post, 'collaborators') and scheduled_post.collaborators:
        collaborators = [c.strip() for c in scheduled_post.collaborators.split(',') if c.strip()]

    # Location
    location_id = None
    location_name = None
    if hasattr(scheduled_post, 'location') and scheduled_post.location:
        location_id = scheduled_post.location.facebook_page_id
        location_name = scheduled_post.location.name

    # Fediverse fields
    spoiler = getattr(scheduled_post, 'spoiler_text', '') or ''
    visibility = getattr(scheduled_post, 'visibility', 'public') or 'public'
    language = getattr(scheduled_post, 'language', '') or ''

    # Poll fields
    poll_options = getattr(scheduled_post, 'poll_options', None) or []
    poll_expires_in = getattr(scheduled_post, 'poll_expires_in', None)
    poll_multiple = getattr(scheduled_post, 'poll_multiple', False)
    poll_hide_totals = getattr(scheduled_post, 'poll_hide_totals', False)

    return PostPayload(
        caption=scheduled_post.caption or "",
        hashtags=all_hashtags,
        pinned_hashtags=pinned,
        image_files=[],  # Images handled by platform utils (S3 vs local differs)
        alt_texts=alt_texts,
        location_id=location_id,
        location_name=location_name,
        user_tags=user_tags,
        collaborators=collaborators,
        spoiler_text=spoiler,
        visibility=visibility,
        language=language,
        sensitive=bool(spoiler),
        poll_options=poll_options if isinstance(poll_options, list) else [],
        poll_expires_in=poll_expires_in,
        poll_multiple=poll_multiple,
        poll_hide_totals=poll_hide_totals,
    )
