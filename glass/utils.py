import logging

from django.utils import timezone

from .models import ManualPostTask

logger = logging.getLogger("postflow")


def queue_manual_post(scheduled_post):
    """Ensure a ManualPostTask exists for this post's Glass targets and put it
    in front of the user in the manual queue.

    Idempotent: calling this more than once for the same post never creates a
    second task, and never resurrects a task that has already been completed
    (posted or skipped) by the user.

    If Glass is the *only* platform targeted by the post, the parent
    ScheduledPost is moved to "awaiting_manual" so the cron job stops picking
    it up as "pending". If other platforms are also targeted, the post's
    status is left alone — the API platform utils (mastodon, instagram, etc.)
    are responsible for setting it to "posted"/"failed".
    """
    task, created = ManualPostTask.objects.get_or_create(
        scheduled_post=scheduled_post,
        platform="glass",
    )

    if task.status not in ("posted", "skipped"):
        task.status = "ready"
        task.ready_at = task.ready_at or timezone.now()
        task.save(update_fields=["status", "ready_at"])

    targets_other_platforms = (
        scheduled_post.mastodon_accounts.exists()
        or scheduled_post.mastodon_native_accounts.exists()
        or scheduled_post.instagram_accounts.exists()
        or scheduled_post.linkedin_accounts.exists()
        or scheduled_post.threads_accounts.exists()
    )

    if not targets_other_platforms:
        scheduled_post.status = "awaiting_manual"
        scheduled_post.save(update_fields=["status"])

    return task


def complete_task(task, posted_url=""):
    """Mark a manual task as posted by the user.

    If the parent post was waiting on this manual task alone
    (status="awaiting_manual"), it is flipped to "posted".
    """
    task.status = "posted"
    task.completed_at = timezone.now()
    task.posted_url = posted_url
    task.save(update_fields=["status", "completed_at", "posted_url"])

    post = task.scheduled_post
    if post.status == "awaiting_manual":
        post.status = "posted"
        post.save(update_fields=["status"])

    return task


def skip_task(task):
    """Mark a manual task as skipped because the user chose not to post it.

    Skip semantics: skipping is a deliberate decision not to publish. If the
    parent post was only waiting on this manual task (status=
    "awaiting_manual"), it moves to "deleted" — the same terminal state used
    elsewhere in the app for posts removed from the calendar. This keeps the
    post out of every other queue/report instead of leaving it stuck in
    "awaiting_manual" forever or misrepresenting it as "posted" or "failed".
    """
    task.status = "skipped"
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at"])

    post = task.scheduled_post
    if post.status == "awaiting_manual":
        post.status = "deleted"
        post.save(update_fields=["status"])

    return task
