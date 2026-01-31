"""
Instagram Graph API Client

Provides a robust client for interacting with Instagram's Graph API v22.0.
Includes retry logic, error handling, and rate limit management.

Rate Limits: 200 calls per hour per user
"""
import logging
import time
from typing import Dict, List, Optional, Any
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger('postflow')


class InstagramAPIError(Exception):
    """Custom exception for Instagram API errors"""
    pass


class InstagramAPIClient:
    """
    Client for interacting with Instagram Graph API.

    Designed for Instagram Business accounts with appropriate permissions.
    Handles both basic media fields and insights metrics.
    """

    DEFAULT_TIMEOUT = 30  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2  # exponential backoff base in seconds
    BASE_URL = "https://graph.instagram.com/v22.0"

    def __init__(self, access_token: str):
        """
        Initialize Instagram API client.

        Args:
            access_token: Page access token with instagram_basic and instagram_manage_insights permissions
        """
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PostFlow/1.0 (Instagram Analytics Client)',
        })

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = 'GET'
    ) -> Any:
        """
        Make an API request with retry logic and error handling.

        Args:
            endpoint: API endpoint path (e.g., /me/media)
            params: Query parameters
            method: HTTP method (GET, POST, etc.)

        Returns:
            Parsed JSON response

        Raises:
            InstagramAPIError: On API errors or request failures
        """
        url = f"{self.BASE_URL}{endpoint}"

        # Add access token to params
        if params is None:
            params = {}
        params['access_token'] = self.access_token

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Instagram API {method} request to {endpoint}, attempt {attempt + 1}")

                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=self.DEFAULT_TIMEOUT
                )

                # Check for rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited by Instagram API. Waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    continue

                # Check for server errors (5xx)
                if 500 <= response.status_code < 600:
                    if attempt < self.MAX_RETRIES - 1:
                        wait_time = self.RETRY_BACKOFF_BASE ** attempt
                        logger.warning(f"Server error {response.status_code}, retrying in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise InstagramAPIError(f"Server error: {response.status_code}")

                # Check for client errors (4xx)
                if 400 <= response.status_code < 500:
                    error_msg = f"Client error: {response.status_code}"
                    try:
                        error_data = response.json()
                        if 'error' in error_data:
                            error_detail = error_data['error']
                            if isinstance(error_detail, dict):
                                error_msg = f"{error_msg} - {error_detail.get('message', error_data)}"
                            else:
                                error_msg = f"{error_msg} - {error_detail}"
                    except:
                        error_msg = f"{error_msg} - {response.text[:200]}"
                    raise InstagramAPIError(error_msg)

                # Success
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        raise InstagramAPIError(f"Invalid JSON response: {e}")

                # Unexpected status code
                raise InstagramAPIError(f"Unexpected status code: {response.status_code}")

            except (Timeout, ConnectionError) as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_BACKOFF_BASE ** attempt
                    logger.warning(f"Request failed ({e}), retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Request failed after {self.MAX_RETRIES} attempts: {e}")
                    raise InstagramAPIError(f"Request failed: {e}")

            except RequestException as e:
                logger.error(f"Request error: {e}")
                raise InstagramAPIError(f"Request error: {e}")

        # Should not reach here, but just in case
        raise InstagramAPIError(f"Request failed after {self.MAX_RETRIES} attempts")

    def get_user_media(self, ig_user_id: str, limit: int = 50) -> List[Dict]:
        """
        Fetch media posts for an Instagram Business user.

        Args:
            ig_user_id: Instagram Business account ID
            limit: Maximum number of posts to fetch (default 50)

        Returns:
            List of media dictionaries with basic fields
        """
        endpoint = f"/{ig_user_id}/media"
        params = {
            'fields': 'id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count',
            'limit': limit
        }

        try:
            response_data = self._make_request(endpoint, params)
            media_list = response_data.get('data', [])
            logger.info(f"Fetched {len(media_list)} media posts for user {ig_user_id}")
            return media_list

        except InstagramAPIError as e:
            logger.error(f"Failed to fetch media for user {ig_user_id}: {e}")
            raise

    def get_media_insights(self, media_id: str) -> Dict[str, int]:
        """
        Fetch insights for a specific media post.

        Insights include: engagement, saved, reach, impressions, video_views (for Reels).
        Requires instagram_manage_insights permission.

        Args:
            media_id: Instagram media ID

        Returns:
            Dictionary mapping metric names to values

        Raises:
            InstagramAPIError: If insights are unavailable or API error occurs
        """
        endpoint = f"/{media_id}/insights"
        params = {
            'metric': 'engagement,saved,reach,impressions,video_views'
        }

        try:
            response_data = self._make_request(endpoint, params)
            insights_data = response_data.get('data', [])

            # Parse insights into a simple dict
            insights = {}
            for metric in insights_data:
                metric_name = metric.get('name')
                metric_values = metric.get('values', [])
                if metric_values and len(metric_values) > 0:
                    insights[metric_name] = metric_values[0].get('value', 0)

            logger.debug(f"Fetched insights for media {media_id}: {insights}")
            return insights

        except InstagramAPIError as e:
            # Insights may not be available for all media types or older posts
            logger.warning(f"Failed to fetch insights for media {media_id}: {e}")
            # Return empty insights instead of raising
            return {}

    def get_media_comments(self, media_id: str) -> List[Dict]:
        """
        Fetch comments for a media post.

        Args:
            media_id: Instagram media ID

        Returns:
            List of comment dictionaries with fields: id, text, username, timestamp, like_count
        """
        endpoint = f"/{media_id}/comments"
        params = {
            'fields': 'id,text,username,timestamp,like_count'
        }

        try:
            response_data = self._make_request(endpoint, params)
            comments = response_data.get('data', [])
            logger.info(f"Fetched {len(comments)} comments for media {media_id}")
            return comments

        except InstagramAPIError as e:
            logger.error(f"Failed to fetch comments for media {media_id}: {e}")
            # Return empty list instead of raising
            return []

    def get_comment_replies(self, comment_id: str) -> List[Dict]:
        """
        Fetch replies to a specific comment.

        Args:
            comment_id: Instagram comment ID

        Returns:
            List of reply dictionaries (same structure as comments)
        """
        endpoint = f"/{comment_id}/replies"
        params = {
            'fields': 'id,text,username,timestamp,like_count'
        }

        try:
            response_data = self._make_request(endpoint, params)
            replies = response_data.get('data', [])
            logger.debug(f"Fetched {len(replies)} replies for comment {comment_id}")
            return replies

        except InstagramAPIError as e:
            logger.warning(f"Failed to fetch replies for comment {comment_id}: {e}")
            return []
