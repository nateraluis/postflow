"""
Mastodon Analytics Fetcher Service

Service layer that uses the Mastodon API client to fetch and save analytics data.
Manages the synchronization of posts and engagement metrics.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dateutil.parser import parse
from django.utils import timezone
from django.db import transaction

from postflow.models import ScheduledPost
from mastodon_native.models import MastodonAccount
from .models import (
    MastodonPost,
    MastodonFavourite,
    MastodonReply,
    MastodonReblog,
    MastodonEngagementSummary
)
from .mastodon_client import MastodonAnalyticsClient, MastodonAPIError

logger = logging.getLogger('postflow')


class MastodonAnalyticsFetcher:
    """
    Service for fetching and storing Mastodon analytics data.

    Handles synchronization of posts and engagement metrics from Mastodon
    to the local database for analytics tracking.
    """

    def __init__(self, account: MastodonAccount):
        """
        Initialize fetcher for a specific Mastodon account.

        Args:
            account: MastodonAccount instance
        """
        self.account = account
        self.client = MastodonAnalyticsClient(
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
            except MastodonAPIError as e:
                logger.error(f"Failed to get account info: {e}")
                raise

        return self._account_info

    def sync_account_posts(self, limit: Optional[int] = 50, exclude_replies: bool = False) -> Tuple[int, int]:
        """
        Fetch posts from Mastodon and create/update MastodonPost records.

        Args:
            limit: Maximum number of posts to fetch. Pass None to fetch all posts. (default 50)
            exclude_replies: If True, exclude replies to focus on original content (default False)

        Returns:
            Tuple of (created_count, updated_count)
        """
        if limit is None:
            logger.info(f"Syncing ALL posts for {self.account}")
        else:
            logger.info(f"Syncing up to {limit} posts for {self.account}")

        try:
            # Get account info to get the account ID
            account_info = self._get_account_info()
            account_id = account_info['id']

            # Fetch posts from API
            posts = self.client.get_user_posts(account_id, limit=limit, exclude_replies=exclude_replies)

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

        except MastodonAPIError as e:
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

        # Parse timestamps
        posted_at = parse(post_data['created_at'])
        if timezone.is_naive(posted_at):
            posted_at = timezone.make_aware(posted_at)

        edited_at = None
        if post_data.get('edited_at'):
            edited_at = parse(post_data['edited_at'])
            if timezone.is_naive(edited_at):
                edited_at = timezone.make_aware(edited_at)

        # Extract media information
        media_attachments = post_data.get('media_attachments', [])
        media_url = ''
        media_type = 'unknown'

        if media_attachments:
            # Get first media attachment
            media = media_attachments[0]
            media_url = media.get('url', '')
            media_type = media.get('type', 'image').lower()

            # Map media type
            if media_type in ['image', 'video', 'gifv', 'audio']:
                pass  # Keep as is
            else:
                media_type = 'unknown'

        # Extract content (handle HTML content)
        content = post_data.get('content', '')
        # Remove HTML tags if present (basic cleanup)
        if '<p>' in content or '<br' in content:
            import re
            content = re.sub('<[^<]+?>', '', content)

        # Build post URL
        post_url = post_data.get('url', f"{self.account.instance_url}/@{account_info['username']}/{post_id}")

        # Extract metadata
        visibility = post_data.get('visibility', 'public')
        language = post_data.get('language') or None  # Store None instead of empty string
        sensitive = post_data.get('sensitive', False)
        spoiler_text = post_data.get('spoiler_text') or None  # Store None instead of empty string

        # Extract threading information
        in_reply_to_id = post_data.get('in_reply_to_id')
        if in_reply_to_id:
            in_reply_to_id = str(in_reply_to_id)
        else:
            in_reply_to_id = None

        in_reply_to_account_id = post_data.get('in_reply_to_account_id')
        if in_reply_to_account_id:
            in_reply_to_account_id = str(in_reply_to_account_id)
        else:
            in_reply_to_account_id = None

        # Extract aggregate metrics from API
        api_replies_count = post_data.get('replies_count', 0)
        api_reblogs_count = post_data.get('reblogs_count', 0)
        api_favourites_count = post_data.get('favourites_count', 0)

        # Try to link to ScheduledPost if this was posted via PostFlow
        scheduled_post = None
        try:
            scheduled_post = ScheduledPost.objects.filter(
                mastodon_post_id=post_id,
                user=self.account.user
            ).first()
        except Exception as e:
            logger.debug(f"Could not link to ScheduledPost: {e}")

        # Create or update MastodonPost
        with transaction.atomic():
            post, created = MastodonPost.objects.update_or_create(
                mastodon_post_id=post_id,
                defaults={
                    'account': self.account,
                    'instance_url': self.account.instance_url,
                    'username': account_info['username'],
                    'content': content,
                    'media_url': media_url,
                    'media_type': media_type,
                    'post_url': post_url,
                    'posted_at': posted_at,
                    'edited_at': edited_at,
                    'scheduled_post': scheduled_post,
                    # Metadata
                    'visibility': visibility,
                    'language': language,
                    'sensitive': sensitive,
                    'spoiler_text': spoiler_text,
                    # Threading
                    'in_reply_to_id': in_reply_to_id,
                    'in_reply_to_account_id': in_reply_to_account_id,
                    # API aggregate metrics
                    'api_replies_count': api_replies_count,
                    'api_reblogs_count': api_reblogs_count,
                    'api_favourites_count': api_favourites_count,
                }
            )

            if created:
                logger.debug(f"Created MastodonPost for {post_id}")
            else:
                logger.debug(f"Updated MastodonPost for {post_id}")

        return created, not created

    def fetch_post_engagement(self, post: MastodonPost) -> Dict[str, int]:
        """
        Fetch favourites, replies, and reblogs for a MastodonPost.

        Args:
            post: MastodonPost instance to fetch engagement for

        Returns:
            Dictionary with engagement counts
        """
        logger.info(f"Fetching engagement for post {post.mastodon_post_id}")

        counts = {
            'favourites': 0,
            'replies': 0,
            'reblogs': 0,
            'errors': []
        }

        # Fetch favourites
        try:
            favourites = self.client.get_post_favourites(post.mastodon_post_id)
            counts['favourites'] = self._process_favourites(post, favourites)
        except MastodonAPIError as e:
            logger.error(f"Failed to fetch favourites: {e}")
            counts['errors'].append(f"favourites: {e}")

        # Fetch replies
        try:
            replies = self.client.get_post_replies(post.mastodon_post_id)
            counts['replies'] = self._process_replies(post, replies)
        except MastodonAPIError as e:
            logger.error(f"Failed to fetch replies: {e}")
            counts['errors'].append(f"replies: {e}")

        # Fetch reblogs
        try:
            reblogs = self.client.get_post_reblogs(post.mastodon_post_id)
            counts['reblogs'] = self._process_reblogs(post, reblogs)
        except MastodonAPIError as e:
            logger.error(f"Failed to fetch reblogs: {e}")
            counts['errors'].append(f"reblogs: {e}")

        # Update engagement summary
        with transaction.atomic():
            summary, created = MastodonEngagementSummary.objects.get_or_create(post=post)
            summary.update_from_post()
            logger.info(f"Updated engagement summary: {summary.total_engagement} total")

        return counts

    def _process_favourites(self, post: MastodonPost, favourites_data: List[Dict]) -> int:
        """
        Process and store favourites for a post.

        NOTE: The Mastodon API does NOT provide individual favourite timestamps.
        The favourited_by endpoint only returns Account objects without timestamp data.
        We use the current time as an estimate when first discovering a favourite.

        Args:
            post: MastodonPost instance
            favourites_data: List of account dictionaries who favourited

        Returns:
            Number of favourites processed
        """
        count = 0
        for favourite_data in favourites_data:
            account_id = str(favourite_data['id'])
            username = favourite_data.get('username', '')
            display_name = favourite_data.get('display_name', username)

            # Use current time as favourited_at since API doesn't provide individual timestamps
            # The first_seen_at field (auto_now_add) tracks when we discovered this favourite
            favourited_at = timezone.now()

            with transaction.atomic():
                favourite, created = MastodonFavourite.objects.get_or_create(
                    post=post,
                    account_id=account_id,
                    defaults={
                        'username': username,
                        'display_name': display_name,
                        'favourited_at': favourited_at,
                        # first_seen_at is set automatically via auto_now_add
                    }
                )
                if created:
                    count += 1
                    logger.debug(f"Created favourite from @{username}")

        return count

    def _process_replies(self, post: MastodonPost, replies_data: List[Dict]) -> int:
        """
        Process and store replies for a post.

        Args:
            post: MastodonPost instance
            replies_data: List of status dictionaries (replies)

        Returns:
            Number of replies processed
        """
        count = 0
        for reply_data in replies_data:
            reply_id = str(reply_data['id'])
            account = reply_data.get('account', {})
            account_id = str(account.get('id', ''))
            username = account.get('username', '')
            display_name = account.get('display_name', username)

            # Parse reply timestamp
            replied_at = parse(reply_data['created_at'])
            if timezone.is_naive(replied_at):
                replied_at = timezone.make_aware(replied_at)

            # Extract content (remove HTML if present)
            content = reply_data.get('content', '')
            if '<p>' in content or '<br' in content:
                import re
                content = re.sub('<[^<]+?>', '', content)

            # Get parent reply ID if this is a reply to another reply
            in_reply_to_id = reply_data.get('in_reply_to_id')
            if in_reply_to_id:
                in_reply_to_id = str(in_reply_to_id)

            with transaction.atomic():
                reply, created = MastodonReply.objects.update_or_create(
                    reply_id=reply_id,
                    defaults={
                        'post': post,
                        'account_id': account_id,
                        'username': username,
                        'display_name': display_name,
                        'content': content,
                        'in_reply_to_id': in_reply_to_id,
                        'replied_at': replied_at,
                    }
                )
                if created:
                    count += 1
                    logger.debug(f"Created reply from @{username}")
                else:
                    logger.debug(f"Updated reply from @{username}")

        return count

    def _process_reblogs(self, post: MastodonPost, reblogs_data: List[Dict]) -> int:
        """
        Process and store reblogs/boosts for a post.

        NOTE: The Mastodon API does NOT provide individual reblog timestamps.
        The reblogged_by endpoint only returns Account objects without timestamp data.
        We use the current time as an estimate when first discovering a reblog.

        Args:
            post: MastodonPost instance
            reblogs_data: List of account dictionaries who reblogged

        Returns:
            Number of reblogs processed
        """
        count = 0
        for reblog_data in reblogs_data:
            account_id = str(reblog_data['id'])
            username = reblog_data.get('username', '')
            display_name = reblog_data.get('display_name', username)

            # Use current time as reblogged_at since API doesn't provide individual timestamps
            # The first_seen_at field (auto_now_add) tracks when we discovered this reblog
            reblogged_at = timezone.now()

            with transaction.atomic():
                reblog, created = MastodonReblog.objects.get_or_create(
                    post=post,
                    account_id=account_id,
                    defaults={
                        'username': username,
                        'display_name': display_name,
                        'reblogged_at': reblogged_at,
                        # first_seen_at is set automatically via auto_now_add
                    }
                )
                if created:
                    count += 1
                    logger.debug(f"Created reblog from @{username}")

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
        posts = MastodonPost.objects.filter(account=self.account).order_by('-posted_at')

        if limit_posts:
            posts = posts[:limit_posts]

        total_summary = {
            'posts_processed': 0,
            'total_favourites': 0,
            'total_replies': 0,
            'total_reblogs': 0,
            'errors': []
        }

        for post in posts:
            try:
                engagement = self.fetch_post_engagement(post)
                total_summary['posts_processed'] += 1
                total_summary['total_favourites'] += engagement['favourites']
                total_summary['total_replies'] += engagement['replies']
                total_summary['total_reblogs'] += engagement['reblogs']

                if engagement.get('errors'):
                    total_summary['errors'].extend(engagement['errors'])

            except Exception as e:
                logger.error(f"Failed to fetch engagement for post {post.mastodon_post_id}: {e}")
                total_summary['errors'].append(f"Post {post.mastodon_post_id}: {e}")

        logger.info(
            f"Engagement fetch complete: {total_summary['posts_processed']} posts, "
            f"{total_summary['total_favourites']} favourites, "
            f"{total_summary['total_replies']} replies, "
            f"{total_summary['total_reblogs']} reblogs"
        )

        return total_summary
