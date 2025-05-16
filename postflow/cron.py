from .models import ScheduledPost
import pytz
import datetime
from .utils import post_pixelfed, post_instagram


def post_scheduled():
    # Get the current UTC date time
    now = datetime.datetime.now(pytz.utc)
    # Get all scheduled post with status pending, and postdate <= now
    posts = ScheduledPost.objects.filter(status="pending", post_date__lte=now)
    for post in posts:
        # Get the image path
        post_pixelfed(post)
        post_instagram(post)
