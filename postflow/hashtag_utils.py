"""
Hashtag validation utilities for PostFlow.
Handles banned hashtag checking, platform limits, and rotation logic.
"""
import json
import os
import logging
from pathlib import Path

logger = logging.getLogger("postflow")

# Load banned hashtags once at module level
_BANNED_HASHTAGS = None
_BANNED_HASHTAGS_FILE = Path(__file__).parent / "banned_hashtags.json"


def get_banned_hashtags() -> set[str]:
    """Load and cache the banned hashtags set."""
    global _BANNED_HASHTAGS
    if _BANNED_HASHTAGS is None:
        try:
            with open(_BANNED_HASHTAGS_FILE) as f:
                data = json.load(f)
                _BANNED_HASHTAGS = {h.lower().lstrip("#") for h in data.get("banned", [])}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load banned hashtags: {e}")
            _BANNED_HASHTAGS = set()
    return _BANNED_HASHTAGS


def reload_banned_hashtags():
    """Force reload of banned hashtags (e.g., after config update)."""
    global _BANNED_HASHTAGS
    _BANNED_HASHTAGS = None
    return get_banned_hashtags()


def check_banned_hashtags(hashtag_names: list[str]) -> list[str]:
    """
    Check a list of hashtag names (without #) against the banned list.
    Returns list of banned hashtags found.
    """
    banned = get_banned_hashtags()
    return [h for h in hashtag_names if h.lower().lstrip("#") in banned]


def validate_hashtags_for_instagram(hashtag_names: list[str]) -> dict:
    """
    Validate hashtags for Instagram posting.
    Returns dict with 'valid', 'errors', and 'warnings' keys.
    """
    result = {"valid": True, "errors": [], "warnings": [], "banned": []}

    # Check count limit
    if len(hashtag_names) > 5:
        result["warnings"].append(
            f"Instagram allows max 5 hashtags. You have {len(hashtag_names)}. "
            f"PostFlow will auto-select the best 5."
        )

    # Check for banned hashtags
    banned = check_banned_hashtags(hashtag_names)
    if banned:
        result["valid"] = False
        result["banned"] = banned
        result["errors"].append(
            f"Banned hashtags detected: {', '.join('#' + h for h in banned)}. "
            f"These may cause shadowbanning on Instagram."
        )

    return result


def select_hashtags_for_platform(
    all_hashtags: list[str],
    pinned_hashtags: list[str],
    platform: str,
    recent_usage: dict[str, int] | None = None,
) -> list[str]:
    """
    Select hashtags for a specific platform, respecting limits and rotation.

    Args:
        all_hashtags: All available hashtags (without #)
        pinned_hashtags: Hashtags that must always be included (without #)
        platform: Target platform
        recent_usage: Dict of hashtag -> usage count for rotation
    Returns:
        List of selected hashtags (without #)
    """
    if platform != "instagram":
        # No limit for Mastodon/Pixelfed
        return list(dict.fromkeys(pinned_hashtags + all_hashtags))

    # Instagram: max 5, pinned first
    selected = list(pinned_hashtags)
    remaining = [h for h in all_hashtags if h not in selected]

    # Filter out banned hashtags
    banned = get_banned_hashtags()
    remaining = [h for h in remaining if h.lower() not in banned]
    selected = [h for h in selected if h.lower() not in banned]

    slots = 5 - len(selected)
    if slots <= 0:
        return selected[:5]

    if recent_usage:
        # Sort by least-recently-used for rotation
        remaining.sort(key=lambda h: recent_usage.get(h, 0))

    selected.extend(remaining[:slots])
    return selected
