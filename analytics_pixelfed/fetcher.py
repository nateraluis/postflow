"""
Pixelfed Analytics Fetcher Service

Service layer that uses the Pixelfed API client to fetch and save analytics data.
Manages the synchronization of posts and engagement metrics.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dateutil.parser import parse
from django.utils import timezone
from django.db import transaction

from pixelfed.models import MastodonAccount
from postflow.models import ScheduledPost
from .models import (
    PixelfedPost,
    PixelfedLike,
    PixelfedComment,
    PixelfedShare,
    PixelfedEngagementSummary
)
from .pixelfed_client import PixelfedAPIClient, PixelfedAPIError

logger = logging.getLogger('postflow')


class PixelfedAnalyticsFetcher:
    """
    Service for fetching and storing Pixelfed analytics data.

    Handles synchronization of posts and engagement metrics from Pixelfed
    to the local database for analytics tracking.
    """

    def __init__(self, account: MastodonAccount):
        """
        Initialize fetcher for a specific Pixelfed account.

        Args:
            account: MastodonAccount instance (works for Pixelfed too)
        """
        self.account = account
        self.client = PixelfedAPIClient(
            instance_url=account.instance_url,
            access_token=account.access_token
        )
        # Cache the account info for this session
        self._account_info = None

    def _get_account_info(self) -> Dict:
        """
        Get cached account info or fetch it from API.

        Returns:
            Account information dictionary
        """
        if not self._account_info:
            try:
                self._account_info = self.client.verify_credentials()
            except PixelfedAPIError as e:
                logger.error(f"Failed to get account info: {e}")
                raise

        return self._account_info

    def sync_account_posts(self, limit: int = 50) -> Tuple[int, int]:
        """
        Fetch posts from Pixelfed and create/update PixelfedPost records.

        Args:
            limit: Maximum number of posts to fetch (default 50)

        Returns:
            Tuple of (created_count, updated_count)
        """
        logger.info(f"Syncing posts for {self.account}")

        try:
            # Get account info to get the account ID
            account_info = self._get_account_info()
            account_id = account_info['id']

            # Fetch posts from API
            posts = self.client.get_user_posts(account_id, limit=limit)

            created_count = 0
            updated_count = 0

            for post_data in posts:
                created, updated = self._process_post(post_data, account_info)
                if created:
                    created_count += 1
                elif updated:
                    updated_count += 1

            logger.info(f"Sync complete: {created_count} created, {updated_count} updated")
            return created_count, updated_count

        except PixelfedAPIError as e:
            logger.error(f"Failed to sync posts: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during sync: {e}")
            raise

    def _process_post(self, post_data: Dict, account_info: Dict) -> Tuple[bool, bool]:
        """
        Process a single post from the API response.

        Args:
            post_data: Post data from API
            account_info: Account information

        Returns:
            Tuple of (created, updated) booleans
        """
        post_id = str(post_data['id'])

        # Parse timestamp
        posted_at = parse(post_data['created_at'])
        if timezone.is_naive(posted_at):
            posted_at = timezone.make_aware(posted_at)

        # Extract media information
        media_attachments = post_data.get('media_attachments', [])
        if not media_attachments:
            logger.debug(f"Skipping post {post_id} - no media attachments")
            return False, False

        # Get first media attachment
        media = media_attachments[0]
        media_url = media.get('url', '')
        media_type = media.get('type', 'image').lower()

        # Map media type
        if media_type == 'video':
            media_type = 'video'
        elif len(media_attachments) > 1:
            media_type = 'carousel'
        else:
            media_type = 'image'

        # Extract caption (handle HTML content)
        caption = post_data.get('content', '')
        # Remove HTML tags if present (basic cleanup)
        if '<p>' in caption:
            import re
            caption = re.sub('<[^<]+?>', '', caption)

        # Build post URL
        post_url = post_data.get('url', f"{self.account.instance_url}/p/{account_info['username']}/{post_id}")

        # Try to link to ScheduledPost if this was posted via PostFlow
        scheduled_post = None
        if hasattr(self.account, 'scheduled_posts'):
            # Try to find by pixelfed_post_id
            try:
                scheduled_post = ScheduledPost.objects.filter(
                    pixelfed_post_id=post_id,
                    user=self.account.user
                ).first()
            except Exception as e:
                logger.debug(f"Could not link to ScheduledPost: {e}")

        # Create or update PixelfedPost
        with transaction.atomic():
            post, created = PixelfedPost.objects.update_or_create(
                pixelfed_post_id=post_id,
                defaults={
                    'account': self.account,
                    'instance_url': self.account.instance_url,
                    'username': account_info['username'],
                    'caption': caption,
                    'media_url': media_url,
                    'media_type': media_type,
                    'post_url': post_url,
                    'posted_at': posted_at,
                    'scheduled_post': scheduled_post,
                }
            )

            if created:
                logger.debug(f"Created PixelfedPost for {post_id}")
            else:
                logger.debug(f"Updated PixelfedPost for {post_id}")

        return created, not created

    def fetch_post_engagement(self, post: PixelfedPost) -> Dict[str, int]:
        """
        Fetch likes, comments, and shares for a PixelfedPost.

        Args:
            post: PixelfedPost instance to fetch engagement for

        Returns:
            Dictionary with engagement counts
        """
        logger.info(f"Fetching engagement for post {post.pixelfed_post_id}")

        counts = {
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'errors': []
        }

        # Fetch likes
        try:
            likes = self.client.get_post_likes(post.pixelfed_post_id)
            counts['likes'] = self._process_likes(post, likes)
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch likes: {e}")
            counts['errors'].append(f"likes: {e}")

        # Fetch comments
        try:
            comments = self.client.get_post_comments(post.pixelfed_post_id)
            counts['comments'] = self._process_comments(post, comments)
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch comments: {e}")
            counts['errors'].append(f"comments: {e}")

        # Fetch shares
        try:
            shares = self.client.get_post_shares(post.pixelfed_post_id)
            counts['shares'] = self._process_shares(post, shares)
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch shares: {e}")
            counts['errors'].append(f"shares: {e}")

        # Update engagement summary
        with transaction.atomic():
            summary, created = PixelfedEngagementSummary.objects.get_or_create(post=post)
            summary.update_from_post()
            logger.info(f"Updated engagement summary: {summary.total_engagement} total")

        return counts

    def _process_likes(self, post: PixelfedPost, likes_data: List[Dict]) -> int:
        """
        Process and store likes for a post.

        Args:
            post: PixelfedPost instance
            likes_data: List of account dictionaries who liked

        Returns:
            Number of likes processed
        """
        count = 0
        for like_data in likes_data:
            account_id = str(like_data['id'])
            username = like_data.get('username', '')
            display_name = like_data.get('display_name', username)

            # Use current time as liked_at since API doesn't provide it
            liked_at = timezone.now()

            with transaction.atomic():
                like, created = PixelfedLike.objects.get_or_create(
                    post=post,
                    account_id=account_id,
                    defaults={
                        'username': username,
                        'display_name': display_name,
                        'liked_at': liked_at,
                    }
                )
                if created:
                    count += 1
                    logger.debug(f"Created like from @{username}")

        return count

    def _process_comments(self, post: PixelfedPost, comments_data: List[Dict]) -> int:
        """
        Process and store comments for a post.

        Args:
            post: PixelfedPost instance
            comments_data: List of status dictionaries (comments/replies)

        Returns:
            Number of comments processed
        """
        count = 0
        for comment_data in comments_data:
            comment_id = str(comment_data['id'])
            account = comment_data.get('account', {})
            account_id = str(account.get('id', ''))
            username = account.get('username', '')
            display_name = account.get('display_name', username)

            # Parse comment timestamp
            commented_at = parse(comment_data['created_at'])
            if timezone.is_naive(commented_at):
                commented_at = timezone.make_aware(commented_at)

            # Extract content (remove HTML if present)
            content = comment_data.get('content', '')
            if '<p>' in content:
                import re
                content = re.sub('<[^<]+?>', '', content)

            # Get parent comment ID if this is a reply to another comment
            in_reply_to_id = comment_data.get('in_reply_to_id')
            if in_reply_to_id:
                in_reply_to_id = str(in_reply_to_id)

            with transaction.atomic():
                comment, created = PixelfedComment.objects.update_or_create(
                    comment_id=comment_id,
                    defaults={
                        'post': post,
                        'account_id': account_id,
                        'username': username,
                        'display_name': display_name,
                        'content': content,
                        'in_reply_to_id': in_reply_to_id,
                        'commented_at': commented_at,
                    }
                )
                if created:
                    count += 1
                    logger.debug(f"Created comment from @{username}")
                else:
                    logger.debug(f"Updated comment from @{username}")

        return count

    def _process_shares(self, post: PixelfedPost, shares_data: List[Dict]) -> int:
        """
        Process and store shares/boosts for a post.

        Args:
            post: PixelfedPost instance
            shares_data: List of account dictionaries who shared

        Returns:
            Number of shares processed
        """
        count = 0
        for share_data in shares_data:
            account_id = str(share_data['id'])
            username = share_data.get('username', '')
            display_name = share_data.get('display_name', username)

            # Use current time as shared_at since API doesn't provide it
            shared_at = timezone.now()

            with transaction.atomic():
                share, created = PixelfedShare.objects.get_or_create(
                    post=post,
                    account_id=account_id,
                    defaults={
                        'username': username,
                        'display_name': display_name,
                        'shared_at': shared_at,
                    }
                )
                if created:
                    count += 1
                    logger.debug(f"Created share from @{username}")

        return count

    def fetch_all_engagement(self, limit_posts: Optional[int] = None) -> Dict:
        """
        Fetch engagement for multiple posts from this account.

        Args:
            limit_posts: Maximum number of posts to process (None for all)

        Returns:
            Summary dictionary with total counts and errors
        """
        logger.info(f"Fetching engagement for all posts from {self.account}")

        # Get posts for this account
        posts = PixelfedPost.objects.filter(account=self.account).order_by('-posted_at')

        if limit_posts:
            posts = posts[:limit_posts]

        total_summary = {
            'posts_processed': 0,
            'total_likes': 0,
            'total_comments': 0,
            'total_shares': 0,
            'errors': []
        }

        for post in posts:
            try:
                engagement = self.fetch_post_engagement(post)
                total_summary['posts_processed'] += 1
                total_summary['total_likes'] += engagement['likes']
                total_summary['total_comments'] += engagement['comments']
                total_summary['total_shares'] += engagement['shares']

                if engagement.get('errors'):
                    total_summary['errors'].extend(engagement['errors'])

            except Exception as e:
                logger.error(f"Failed to fetch engagement for post {post.pixelfed_post_id}: {e}")
                total_summary['errors'].append(f"Post {post.pixelfed_post_id}: {e}")

        logger.info(
            f"Engagement fetch complete: {total_summary['posts_processed']} posts, "
            f"{total_summary['total_likes']} likes, "
            f"{total_summary['total_comments']} comments, "
            f"{total_summary['total_shares']} shares"
        )

        return total_summary