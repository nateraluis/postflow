"""Posting-slot proposal and evergreen content rotation."""
from datetime import timedelta

from django.utils import timezone

from analytics.utils import get_best_posting_times
from postflow.models import ScheduledPost

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def propose_slots(user, count=3, horizon_days=14):
    """Propose posting datetimes over the coming days, preferring the user's
    historically best times and avoiding collisions with already-scheduled posts."""
    best = get_best_posting_times(user)
    preferred = [
        (DAY_NAMES.index(s["day"]), s["hour"])
        for s in best.get("suggestions", [])
        if s.get("day") in DAY_NAMES
    ] or [(2, 9), (3, 12), (2, 18)]

    now = timezone.now()
    taken = set(
        ScheduledPost.objects.filter(
            user=user,
            post_date__gte=now,
            post_date__lte=now + timedelta(days=horizon_days),
        )
        .exclude(status="deleted")
        .values_list("post_date", flat=True)
    )
    taken_hours = {(t.date(), t.hour) for t in taken}

    slots = []
    day = now.date()
    while len(slots) < count and day <= (now + timedelta(days=horizon_days)).date():
        for dow, hour in preferred:
            if len(slots) >= count:
                break
            if day.weekday() != dow:
                continue
            candidate = timezone.make_aware(
                timezone.datetime(day.year, day.month, day.day, hour, 0),
                timezone.get_current_timezone(),
            )
            if candidate <= now or (day, hour) in taken_hours:
                continue
            slots.append(candidate)
        day += timedelta(days=1)

    # Fallback: spread evenly if preferred weekdays don't yield enough slots
    while len(slots) < count:
        base = slots[-1] if slots else now + timedelta(hours=3)
        slots.append(base + timedelta(days=2))

    return sorted(slots)[:count]


def pick_evergreen(website, exclude_recent=3):
    """Pick the best archive post to re-promote: least-recently promoted first,
    never-promoted posts before all others, skipping the newest posts."""
    posts = website.posts.order_by("-published_at")
    recent_ids = list(posts.values_list("id", flat=True)[:exclude_recent])
    candidates = website.posts.exclude(id__in=recent_ids)
    never = candidates.filter(last_promoted_at__isnull=True).order_by("-published_at")
    if never.exists():
        return never.first()
    return candidates.order_by("last_promoted_at").first()
