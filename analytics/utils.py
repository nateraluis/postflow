"""
Utility functions for fetching analytics from social media APIs.
"""
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("postflow")


class AnalyticsFetchError(Exception):
    """Raised when analytics cannot be fetched from an API."""
    pass


def fetch_instagram_analytics(post_id: str, access_token: str) -> Dict[str, int]:
    """
    Fetch analytics for an Instagram post using the Graph API.

    Args:
        post_id: Instagram media/post ID
        access_token: Instagram Business Account access token

    Returns:
        Dictionary with analytics metrics:
        {
            'likes': int,
            'comments': int,
            'shares': int,
            'impressions': int,
            'reach': int,
            'saved': int
        }

    Raises:
        AnalyticsFetchError: If API request fails
    """
    try:
        # Fetch post insights
        insights_url = f"https://graph.facebook.com/v18.0/{post_id}/insights"
        params = {
            'metric': 'impressions,reach,saved',
            'access_token': access_token
        }

        insights_response = requests.get(insights_url, params=params, timeout=10)
        insights_response.raise_for_status()
        insights_data = insights_response.json()

        # Fetch basic post data (likes, comments)
        post_url = f"https://graph.facebook.com/v18.0/{post_id}"
        post_params = {
            'fields': 'like_count,comments_count',
            'access_token': access_token
        }

        post_response = requests.get(post_url, params=post_params, timeout=10)
        post_response.raise_for_status()
        post_data = post_response.json()

        # Parse insights
        metrics = {
            'likes': post_data.get('like_count', 0),
            'comments': post_data.get('comments_count', 0),
            'shares': 0,  # Instagram doesn't provide share count via API
            'impressions': 0,
            'reach': 0,
            'saved': 0,
        }

        # Extract insights data
        for insight in insights_data.get('data', []):
            metric_name = insight.get('name')
            values = insight.get('values', [])
            if values:
                value = values[0].get('value', 0)
                if metric_name == 'impressions':
                    metrics['impressions'] = value
                elif metric_name == 'reach':
                    metrics['reach'] = value
                elif metric_name == 'saved':
                    metrics['saved'] = value

        logger.info(f"Fetched Instagram analytics for post {post_id}: {metrics}")
        return metrics

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Instagram analytics for post {post_id}: {e}")
        raise AnalyticsFetchError(f"Instagram API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching Instagram analytics: {e}")
        raise AnalyticsFetchError(f"Unexpected error: {e}")


def fetch_mastodon_analytics(post_id: str, instance_url: str, access_token: str) -> Dict[str, int]:
    """
    Fetch analytics for a Mastodon post.

    Args:
        post_id: Mastodon status ID
        instance_url: Mastodon instance URL (e.g., https://mastodon.social)
        access_token: User's access token for the instance

    Returns:
        Dictionary with analytics metrics:
        {
            'likes': int (favourites),
            'comments': int (replies),
            'shares': int (reblogs),
            'impressions': None,
            'reach': None,
            'saved': 0
        }

    Raises:
        AnalyticsFetchError: If API request fails
    """
    try:
        # Ensure instance_url doesn't end with /
        instance_url = instance_url.rstrip('/')

        # Fetch status data
        status_url = f"{instance_url}/api/v1/statuses/{post_id}"
        headers = {'Authorization': f'Bearer {access_token}'}

        response = requests.get(status_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        metrics = {
            'likes': data.get('favourites_count', 0),
            'comments': data.get('replies_count', 0),
            'shares': data.get('reblogs_count', 0),
            'impressions': None,  # Not available on Mastodon
            'reach': None,  # Not available on Mastodon
            'saved': 0,  # Not available on Mastodon
        }

        logger.info(f"Fetched Mastodon analytics for post {post_id}: {metrics}")
        return metrics

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Mastodon analytics for post {post_id}: {e}")
        raise AnalyticsFetchError(f"Mastodon API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching Mastodon analytics: {e}")
        raise AnalyticsFetchError(f"Unexpected error: {e}")


def fetch_pixelfed_analytics(post_id: str, instance_url: str, access_token: str) -> Dict[str, int]:
    """
    Fetch analytics for a Pixelfed post.

    Pixelfed uses the same API structure as Mastodon, so this function
    is essentially the same as fetch_mastodon_analytics.

    Args:
        post_id: Pixelfed status ID
        instance_url: Pixelfed instance URL (e.g., https://pixelfed.social)
        access_token: User's access token for the instance

    Returns:
        Dictionary with analytics metrics:
        {
            'likes': int (favourites),
            'comments': int (replies),
            'shares': int (shares/reblogs),
            'impressions': None,
            'reach': None,
            'saved': 0
        }

    Raises:
        AnalyticsFetchError: If API request fails
    """
    try:
        # Pixelfed uses the same API as Mastodon
        # Ensure instance_url doesn't end with /
        instance_url = instance_url.rstrip('/')

        # Fetch status data
        status_url = f"{instance_url}/api/v1/statuses/{post_id}"
        headers = {'Authorization': f'Bearer {access_token}'}

        response = requests.get(status_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        metrics = {
            'likes': data.get('favourites_count', 0),
            'comments': data.get('replies_count', 0),
            'shares': data.get('reblogs_count', 0),  # Pixelfed may use 'shares_count'
            'impressions': None,  # Not available on Pixelfed
            'reach': None,  # Not available on Pixelfed
            'saved': 0,  # Not available on Pixelfed
        }

        # Pixelfed might use 'shares_count' instead of 'reblogs_count'
        if 'shares_count' in data:
            metrics['shares'] = data.get('shares_count', 0)

        logger.info(f"Fetched Pixelfed analytics for post {post_id}: {metrics}")
        return metrics

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Pixelfed analytics for post {post_id}: {e}")
        raise AnalyticsFetchError(f"Pixelfed API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching Pixelfed analytics: {e}")
        raise AnalyticsFetchError(f"Unexpected error: {e}")
