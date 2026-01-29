"""
Pixelfed API Client

Provides a robust client for interacting with Pixelfed's Mastodon-compatible API.
Includes retry logic, error handling, and comprehensive logging.
"""
import logging
import time
from typing import Dict, List, Optional, Any
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger('postflow')


class PixelfedAPIError(Exception):
    """Custom exception for Pixelfed API errors"""
    pass


class PixelfedAPIClient:
    """
    Client for interacting with Pixelfed API.

    Pixelfed uses the Mastodon-compatible API, so endpoints follow Mastodon patterns.
    """

    DEFAULT_TIMEOUT = 30  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2  # exponential backoff base in seconds

    def __init__(self, instance_url: str, access_token: str):
        """
        Initialize Pixelfed API client.

        Args:
            instance_url: Base URL of the Pixelfed instance (e.g., https://pixelfed.social)
            access_token: OAuth access token for authentication
        """
        self.instance_url = instance_url.rstrip('/')
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'PostFlow/1.0 (Pixelfed Analytics Client)',
        })

    def _make_request(
        self,
        endpoint: str,
        method: str = 'GET',
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Any:
        """
        Make an API request with retry logic and error handling.

        Args:
            endpoint: API endpoint path (e.g., /api/v1/accounts/123/statuses)
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Request body data

        Returns:
            Parsed JSON response

        Raises:
            PixelfedAPIError: On API errors or request failures
        """
        url = f"{self.instance_url}{endpoint}"

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Pixelfed API {method} request to {url}, attempt {attempt + 1}")

                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    timeout=self.DEFAULT_TIMEOUT
                )

                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('X-RateLimit-Reset', 60))
                    logger.warning(f"Rate limited by Pixelfed. Waiting {retry_after} seconds")
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
                        raise PixelfedAPIError(f"Server error: {response.status_code}")

                # Check for client errors (4xx)
                if 400 <= response.status_code < 500:
                    error_msg = f"Client error: {response.status_code}"
                    try:
                        error_data = response.json()
                        if 'error' in error_data:
                            error_msg = f"{error_msg} - {error_data['error']}"
                    except:
                        error_msg = f"{error_msg} - {response.text[:200]}"
                    raise PixelfedAPIError(error_msg)

                # Success
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        raise PixelfedAPIError(f"Invalid JSON response: {e}")

                # Unexpected status code
                raise PixelfedAPIError(f"Unexpected status code: {response.status_code}")

            except (Timeout, ConnectionError) as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_BACKOFF_BASE ** attempt
                    logger.warning(f"Request failed ({e}), retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Request failed after {self.MAX_RETRIES} attempts: {e}")
                    raise PixelfedAPIError(f"Request failed: {e}")

            except RequestException as e:
                logger.error(f"Request error: {e}")
                raise PixelfedAPIError(f"Request error: {e}")

        # Should not reach here, but just in case
        raise PixelfedAPIError(f"Request failed after {self.MAX_RETRIES} attempts")

    def get_user_posts(self, account_id: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch user's posts from Pixelfed with pagination support.

        Args:
            account_id: Pixelfed account ID
            limit: Maximum number of posts to fetch. If None, fetches all available posts.

        Returns:
            List of post dictionaries with media
        """
        endpoint = f"/api/v1/accounts/{account_id}/statuses"
        base_params = {
            'only_media': 'true',  # Only fetch posts with media
            'exclude_replies': 'true',  # Exclude replies to focus on original content
        }

        if limit is None:
            logger.info(f"Fetching ALL posts for account {account_id}")
        else:
            logger.info(f"Fetching up to {limit} posts for account {account_id}")

        all_posts = []
        max_id = None
        page = 1

        try:
            while True:
                # Pixelfed API limits each request to 40 posts
                if limit is None:
                    batch_limit = 40  # Fetch max per page when getting all posts
                else:
                    batch_limit = min(40, limit - len(all_posts))

                params = {**base_params, 'limit': batch_limit}
                if max_id:
                    params['max_id'] = max_id

                logger.debug(f"Fetching page {page}, batch_limit={batch_limit}, max_id={max_id}")

                posts_batch = self._make_request(endpoint, params=params)

                if not posts_batch:
                    logger.info(f"No more posts available after page {page}")
                    break

                all_posts.extend(posts_batch)
                logger.debug(f"Fetched {len(posts_batch)} posts on page {page}, total: {len(all_posts)}")

                # If we got fewer posts than requested, we've reached the end
                if len(posts_batch) < batch_limit:
                    logger.info(f"Reached end of posts at page {page}")
                    break

                # If we have a limit and reached it, stop
                if limit is not None and len(all_posts) >= limit:
                    logger.info(f"Reached limit of {limit} posts at page {page}")
                    break

                # Use the last post's ID for pagination
                max_id = posts_batch[-1]['id']
                page += 1

            logger.info(f"Successfully fetched {len(all_posts)} posts across {page} page(s)")
            return all_posts

        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch posts for account {account_id}: {e}")
            raise

    def get_post_likes(self, post_id: str) -> List[Dict]:
        """
        Fetch accounts that liked/favorited a post.

        Args:
            post_id: Pixelfed post ID

        Returns:
            List of account dictionaries who liked the post
        """
        endpoint = f"/api/v1/statuses/{post_id}/favourited_by"

        logger.debug(f"Fetching likes for post {post_id}")

        try:
            likes = self._make_request(endpoint)
            logger.debug(f"Found {len(likes)} likes for post {post_id}")
            return likes
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch likes for post {post_id}: {e}")
            raise

    def get_post_comments(self, post_id: str) -> List[Dict]:
        """
        Fetch comments/replies on a post.

        Args:
            post_id: Pixelfed post ID

        Returns:
            List of comment/status dictionaries (descendants)
        """
        endpoint = f"/api/v1/statuses/{post_id}/context"

        logger.debug(f"Fetching comments for post {post_id}")

        try:
            context = self._make_request(endpoint)
            # Context returns {ancestors: [], descendants: []}
            # Descendants are the replies/comments
            comments = context.get('descendants', [])
            logger.debug(f"Found {len(comments)} comments for post {post_id}")
            return comments
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch comments for post {post_id}: {e}")
            raise

    def get_post_shares(self, post_id: str) -> List[Dict]:
        """
        Fetch accounts that shared/reblogged/boosted a post.

        Args:
            post_id: Pixelfed post ID

        Returns:
            List of account dictionaries who shared the post
        """
        endpoint = f"/api/v1/statuses/{post_id}/reblogged_by"

        logger.debug(f"Fetching shares for post {post_id}")

        try:
            shares = self._make_request(endpoint)
            logger.debug(f"Found {len(shares)} shares for post {post_id}")
            return shares
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch shares for post {post_id}: {e}")
            raise

    def get_account_info(self, account_id: str) -> Dict:
        """
        Fetch account information.

        Args:
            account_id: Pixelfed account ID

        Returns:
            Account information dictionary
        """
        endpoint = f"/api/v1/accounts/{account_id}"

        logger.debug(f"Fetching account info for {account_id}")

        try:
            account = self._make_request(endpoint)
            logger.debug(f"Successfully fetched account info for {account['username']}")
            return account
        except PixelfedAPIError as e:
            logger.error(f"Failed to fetch account info for {account_id}: {e}")
            raise

    def verify_credentials(self) -> Dict:
        """
        Verify the current access token and get authenticated account info.

        Returns:
            Authenticated account information dictionary
        """
        endpoint = "/api/v1/accounts/verify_credentials"

        logger.debug("Verifying API credentials")

        try:
            account = self._make_request(endpoint)
            logger.info(f"Successfully verified credentials for @{account['username']}")
            return account
        except PixelfedAPIError as e:
            logger.error(f"Failed to verify credentials: {e}")
            raise