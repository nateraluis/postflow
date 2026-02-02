"""
Instagram Analytics Fetcher Service

Service layer that uses the Instagram API client to fetch and save analytics data.
Manages the synchronization of posts, insights, and engagement metrics.
"""
import logging
import requests
from io import BytesIO
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dateutil.parser import parse
from django.utils import timezone
from django.db import transaction
from django.core.files.base import ContentFile

from instagram.models import InstagramBusinessAccount
from postflow.models import ScheduledPost
from .models import (
    InstagramPost,
    InstagramComment,
    InstagramEngagementSummary
)
from .instagram_client import InstagramAPIClient, InstagramAPIError

logger = logging.getLogger('postflow')


class InstagramAnalyticsFetcher:
    """
    Service for fetching and storing Instagram analytics data.

    Handles synchronization of posts, insights, and engagement metrics from Instagram
    to the local database for analytics tracking.
    """

    def __init__(self, account: InstagramBusinessAccount):
        """
        Initialize fetcher for a specific Instagram Business account.

        Args:
            account: InstagramBusinessAccount instance
        """
        self.account = account
        self.client = InstagramAPIClient(access_token=account.access_token)

    def _download_and_save_image(self, post: InstagramPost, media_url: str) -> bool:
        """
        Download image from Instagram CDN and save to S3.

        Args:
            post: InstagramPost instance to save image to
            media_url: URL of the image on Instagram CDN

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Download image from Instagram CDN
            response = requests.get(media_url, timeout=30)
            response.raise_for_status()

            # Get file extension from content type or URL
            content_type = response.headers.get('content-type', '')
            if 'image/jpeg' in content_type or 'image/jpg' in content_type:
                ext = 'jpg'
            elif 'image/png' in content_type:
                ext = 'png'
            else:
                # Fallback to jpg
                ext = 'jpg'

            # Create filename
            filename = f"{post.instagram_media_id}.{ext}"

            # Save to the cached_image field (will upload to S3 automatically)
            post.cached_image.save(
                filename,
                ContentFile(response.content),
                save=True
            )

            logger.info(f"Successfully cached image for post {post.instagram_media_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to download/save image for post {post.instagram_media_id}: {e}")
            return False

    def sync_account_posts(self, limit: int = 50) -> Tuple[int, int]:
        """
        Fetch posts from Instagram and create/update InstagramPost records.

        Args:
            limit: Maximum number of posts to fetch (default 50)

        Returns:
            Tuple of (created_count, updated_count)
        """
        logger.info(f"Syncing up to {limit} posts for {self.account}")

        try:
            # Fetch posts from API
            media_list = self.client.get_user_media(self.account.instagram_id, limit=limit)

            created_count = 0
            updated_count = 0

            for media_data in media_list:
                created, updated = self._process_media(media_data)
                if created:
                    created_count += 1
                elif updated:
                    updated_count += 1

            logger.info(f"Sync complete: {created_count} created, {updated_count} updated")
            return created_count, updated_count

        except InstagramAPIError as e:
            logger.error(f"Failed to sync posts: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during sync: {e}")
            raise

    def _process_media(self, media_data: Dict) -> Tuple[bool, bool]:
        """
        Process a single media post from the API response.

        Args:
            media_data: Media data from API

        Returns:
            Tuple of (created, updated) booleans
        """
        media_id = str(media_data['id'])

        # Parse timestamp
        posted_at = parse(media_data['timestamp'])
        if timezone.is_naive(posted_at):
            posted_at = timezone.make_aware(posted_at)

        # Extract media information
        caption = media_data.get('caption', '')
        media_url = media_data.get('media_url', '')
        media_type = media_data.get('media_type', 'IMAGE')
        permalink = media_data.get('permalink', '')

        # Extract basic metrics (available without insights call)
        like_count = media_data.get('like_count', 0)
        comments_count = media_data.get('comments_count', 0)

        # Try to link to ScheduledPost if this was posted via PostFlow
        scheduled_post = None
        try:
            scheduled_post = ScheduledPost.objects.filter(
                instagram_post_id=media_id,
                user=self.account.user
            ).first()
        except Exception as e:
            logger.debug(f"Could not link to ScheduledPost: {e}")

        # Create or update InstagramPost
        with transaction.atomic():
            post, created = InstagramPost.objects.update_or_create(
                instagram_media_id=media_id,
                defaults={
                    'account': self.account,
                    'username': self.account.username,
                    'caption': caption,
                    'media_url': media_url,
                    'media_type': media_type,
                    'permalink': permalink,
                    'posted_at': posted_at,
                    'api_like_count': like_count,
                    'api_comments_count': comments_count,
                    'scheduled_post': scheduled_post,
                }
            )

            if created:
                logger.debug(f"Created new InstagramPost: {media_id}")
            else:
                logger.debug(f"Updated existing InstagramPost: {media_id}")

        # Download and cache the image if we don't have it yet (and it's not a video)
        if media_type != 'VIDEO' and not post.cached_image:
            logger.info(f"Downloading image for post {media_id}")
            self._download_and_save_image(post, media_url)

        # Create or update engagement summary with basic metrics
        post.refresh_engagement_summary()

        return created, not created

    def fetch_post_insights(self, post: InstagramPost) -> Dict[str, int]:
        """
        Fetch insights for a specific post and update the post record.

        Instagram Insights (as of 2025) include:
        - reach: Unique accounts that saw the media
        - saved: Times the media was saved
        - total_interactions: Total interactions (likes + comments + saves + shares)
        - plays: Video plays (VIDEO and REELS only)

        Note: 'impressions' metric was deprecated for media created after July 2, 2024

        Args:
            post: InstagramPost instance

        Returns:
            Dictionary of insights metrics
        """
        logger.info(f"Fetching insights for post {post.instagram_media_id}")

        try:
            # Fetch insights from API with media type
            insights = self.client.get_media_insights(post.instagram_media_id, post.media_type)

            if not insights:
                logger.warning(f"No insights available for post {post.instagram_media_id}")
                return {}

            # Update post with insights
            with transaction.atomic():
                # Map API metrics to model fields
                post.api_engagement = insights.get('total_interactions', 0)
                post.api_saved = insights.get('saved', 0)
                post.api_reach = insights.get('reach', 0)
                # impressions is deprecated, but keep the field for older posts
                post.api_impressions = insights.get('impressions', 0)
                # plays is only available for VIDEO and REELS
                post.api_video_views = insights.get('plays')  # Can be None for non-videos
                post.save()

                # Update engagement summary
                post.refresh_engagement_summary()

            logger.debug(f"Updated insights for post {post.instagram_media_id}: {insights}")
            return insights

        except InstagramAPIError as e:
            logger.error(f"Failed to fetch insights for post {post.instagram_media_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching insights: {e}")
            return {}

    def fetch_post_comments(self, post: InstagramPost) -> int:
        """
        Fetch comments for a specific post and create/update comment records.

        Args:
            post: InstagramPost instance

        Returns:
            Count of new comments created
        """
        logger.info(f"Fetching comments for post {post.instagram_media_id}")

        try:
            # Fetch comments from API
            comments_data = self.client.get_media_comments(post.instagram_media_id)

            new_comments = 0

            for comment_data in comments_data:
                created = self._process_comment(post, comment_data)
                if created:
                    new_comments += 1

                # Fetch replies to this comment
                comment_id = comment_data['id']
                replies = self.client.get_comment_replies(comment_id)
                for reply_data in replies:
                    reply_created = self._process_comment(post, reply_data, parent_id=comment_id)
                    if reply_created:
                        new_comments += 1

            logger.info(f"Fetched {new_comments} new comments for post {post.instagram_media_id}")
            return new_comments

        except InstagramAPIError as e:
            logger.error(f"Failed to fetch comments for post {post.instagram_media_id}: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error fetching comments: {e}")
            return 0

    def _process_comment(
        self,
        post: InstagramPost,
        comment_data: Dict,
        parent_id: Optional[str] = None
    ) -> bool:
        """
        Process a single comment from the API response.

        Args:
            post: InstagramPost this comment belongs to
            comment_data: Comment data from API
            parent_id: Parent comment ID if this is a reply

        Returns:
            True if comment was created, False if it already existed
        """
        comment_id = str(comment_data['id'])

        # Parse timestamp
        timestamp = parse(comment_data['timestamp'])
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp)

        # Extract comment data
        username = comment_data.get('username', '')
        text = comment_data.get('text', '')
        like_count = comment_data.get('like_count', 0)

        # Create or update comment
        with transaction.atomic():
            comment, created = InstagramComment.objects.update_or_create(
                comment_id=comment_id,
                defaults={
                    'post': post,
                    'username': username,
                    'text': text,
                    'timestamp': timestamp,
                    'like_count': like_count,
                    'parent_comment_id': parent_id,
                }
            )

            if created:
                logger.debug(f"Created new comment: {comment_id}")
            else:
                logger.debug(f"Updated existing comment: {comment_id}")

            return created

    def fetch_all_insights(self, limit_posts: Optional[int] = 30) -> Dict:
        """
        Fetch insights for multiple recent posts.

        Args:
            limit_posts: Maximum number of posts to process (default 30 to manage rate limits)

        Returns:
            Summary dictionary with statistics
        """
        logger.info(f"Fetching insights for up to {limit_posts} posts")

        # Get recent posts for this account
        posts = InstagramPost.objects.filter(account=self.account).order_by('-posted_at')
        if limit_posts:
            posts = posts[:limit_posts]

        insights_fetched = 0
        comments_fetched = 0
        errors = 0

        for post in posts:
            try:
                # Fetch insights
                insights = self.fetch_post_insights(post)
                if insights:
                    insights_fetched += 1

                # Fetch comments
                new_comments = self.fetch_post_comments(post)
                comments_fetched += new_comments

            except Exception as e:
                logger.error(f"Error processing post {post.instagram_media_id}: {e}")
                errors += 1

        summary = {
            'posts_processed': len(posts),
            'insights_fetched': insights_fetched,
            'comments_fetched': comments_fetched,
            'errors': errors,
        }

        logger.info(f"Insights fetch complete: {summary}")
        return summary
