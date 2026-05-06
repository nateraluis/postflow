"""
Weekly digest generator for PostFlow.
Aggregates top posts, hashtag performance, and optimal times into a digest.
Rendered online only — no email sending.
"""
import logging
from datetime import timedelta
from django.utils import timezone

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

    return {
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
