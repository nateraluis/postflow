"""
Weekly digest generator for PostFlow.
Aggregates top posts, hashtag performance, and optimal times into a digest.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.template.loader import render_to_string

from analytics.utils import (
    get_top_performers,
    get_hashtag_performance,
    get_best_posting_times,
    get_consistency_score,
)

logger = logging.getLogger("postflow")


def generate_digest(user):
    """
    Generate a weekly digest for a user.
    Returns a dict with digest data suitable for rendering.
    """
    top = get_top_performers(user, days=7, limit=5)
    hashtags = get_hashtag_performance(user, days=7)
    times = get_best_posting_times(user, days=30)
    consistency = get_consistency_score(user, days=7)

    # Build suggestions
    suggestions = []
    if consistency.get('score', 0) < 50:
        suggestions.append("Try posting more consistently. Aim for at least 3 posts per week.")
    if times.get('suggestions'):
        best = times['suggestions'][0]
        suggestions.append(f"Your best posting time is {best['day']} at {best['hour']}:00.")
    if hashtags.get('groups'):
        top_group = hashtags['groups'][0]
        suggestions.append(f"Your top hashtag group is \"{top_group['group_name']}\" with {top_group['avg_engagement']} avg engagement.")
        if len(hashtags['groups']) > 1:
            worst = hashtags['groups'][-1]
            if worst['avg_engagement'] == 0:
                suggestions.append(f"Consider retiring the \"{worst['group_name']}\" hashtag group (0 engagement).")

    digest = {
        'user': user,
        'generated_at': timezone.now(),
        'week_start': (timezone.now() - timedelta(days=7)).date(),
        'week_end': timezone.now().date(),
        'top_posts': top.get('posts', []),
        'hashtag_groups': hashtags.get('groups', [])[:5],
        'best_times': times.get('suggestions', []),
        'consistency': consistency,
        'suggestions': suggestions,
        'has_data': top.get('has_data', False) or hashtags.get('has_data', False),
    }

    return digest


def render_digest_html(user):
    """Render digest as HTML string."""
    digest = generate_digest(user)
    return render_to_string('postflow/emails/weekly_digest.html', {'digest': digest})


def send_weekly_digest(user):
    """Send weekly digest email to a user."""
    from django.core.mail import send_mail
    from django.conf import settings

    digest = generate_digest(user)
    if not digest['has_data']:
        logger.info(f"Skipping digest for {user.email}: no data")
        return False

    html_content = render_to_string('postflow/emails/weekly_digest.html', {'digest': digest})

    try:
        send_mail(
            subject=f"PostFlow Weekly Digest - {digest['week_end'].strftime('%b %d, %Y')}",
            message="",
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@postflow.photo'),
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f"Weekly digest sent to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send digest to {user.email}: {e}")
        return False


def send_all_digests():
    """Send weekly digests to all active users with connected accounts."""
    from postflow.models import CustomUser
    from pixelfed.models import MastodonAccount
    from mastodon_native.models import MastodonAccount as MastodonNativeAccount
    from instagram.models import InstagramBusinessAccount

    users = CustomUser.objects.filter(is_active=True)
    sent = 0
    skipped = 0

    for user in users:
        has_accounts = (
            MastodonAccount.objects.filter(user=user).exists() or
            MastodonNativeAccount.objects.filter(user=user).exists() or
            InstagramBusinessAccount.objects.filter(user=user).exists()
        )
        if has_accounts:
            if send_weekly_digest(user):
                sent += 1
            else:
                skipped += 1
        else:
            skipped += 1

    logger.info(f"Weekly digest: sent {sent}, skipped {skipped}")
    return sent, skipped
