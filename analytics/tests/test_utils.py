"""
Unit tests for analytics utility functions using pytest.
"""
import pytest
import responses
from analytics.utils import (
    fetch_instagram_analytics,
    fetch_mastodon_analytics,
    fetch_pixelfed_analytics,
    AnalyticsFetchError
)


@pytest.mark.django_db
class TestFetchInstagramAnalytics:
    """Tests for Instagram analytics fetching."""

    @responses.activate
    def test_fetch_instagram_analytics_success(self):
        """Test successful Instagram analytics fetch."""
        post_id = '123456'
        access_token = 'test_token'

        # Mock insights API response
        responses.add(
            responses.GET,
            f'https://graph.facebook.com/v18.0/{post_id}/insights',
            json={
                'data': [
                    {'name': 'impressions', 'values': [{'value': 2000}]},
                    {'name': 'reach', 'values': [{'value': 1500}]},
                    {'name': 'saved', 'values': [{'value': 50}]},
                ]
            },
            status=200
        )

        # Mock post data API response
        responses.add(
            responses.GET,
            f'https://graph.facebook.com/v18.0/{post_id}',
            json={
                'like_count': 100,
                'comments_count': 20
            },
            status=200
        )

        metrics = fetch_instagram_analytics(post_id, access_token)

        assert metrics['likes'] == 100
        assert metrics['comments'] == 20
        assert metrics['shares'] == 0  # Instagram doesn't provide
        assert metrics['impressions'] == 2000
        assert metrics['reach'] == 1500
        assert metrics['saved'] == 50

    @responses.activate
    def test_fetch_instagram_analytics_api_error(self):
        """Test Instagram analytics fetch with API error."""
        post_id = '123456'
        access_token = 'test_token'

        # Mock API error
        responses.add(
            responses.GET,
            f'https://graph.facebook.com/v18.0/{post_id}/insights',
            json={'error': {'message': 'Invalid OAuth token'}},
            status=400
        )

        with pytest.raises(AnalyticsFetchError):
            fetch_instagram_analytics(post_id, access_token)

    @responses.activate
    def test_fetch_instagram_analytics_missing_data(self):
        """Test Instagram analytics fetch with missing data."""
        post_id = '123456'
        access_token = 'test_token'

        # Mock minimal response
        responses.add(
            responses.GET,
            f'https://graph.facebook.com/v18.0/{post_id}/insights',
            json={'data': []},
            status=200
        )

        responses.add(
            responses.GET,
            f'https://graph.facebook.com/v18.0/{post_id}',
            json={},
            status=200
        )

        metrics = fetch_instagram_analytics(post_id, access_token)

        # Should have default values
        assert metrics['likes'] == 0
        assert metrics['comments'] == 0
        assert metrics['impressions'] == 0
        assert metrics['reach'] == 0
        assert metrics['saved'] == 0


@pytest.mark.django_db
class TestFetchMastodonAnalytics:
    """Tests for Mastodon analytics fetching."""

    @responses.activate
    def test_fetch_mastodon_analytics_success(self):
        """Test successful Mastodon analytics fetch."""
        post_id = '654321'
        instance_url = 'https://mastodon.social'
        access_token = 'test_token'

        # Mock Mastodon API response
        responses.add(
            responses.GET,
            f'{instance_url}/api/v1/statuses/{post_id}',
            json={
                'favourites_count': 50,
                'replies_count': 10,
                'reblogs_count': 5
            },
            status=200
        )

        metrics = fetch_mastodon_analytics(post_id, instance_url, access_token)

        assert metrics['likes'] == 50
        assert metrics['comments'] == 10
        assert metrics['shares'] == 5
        assert metrics['impressions'] is None
        assert metrics['reach'] is None
        assert metrics['saved'] == 0

    @responses.activate
    def test_fetch_mastodon_analytics_trailing_slash(self):
        """Test Mastodon analytics with trailing slash in URL."""
        post_id = '654321'
        instance_url = 'https://mastodon.social/'  # With trailing slash
        access_token = 'test_token'

        # URL should be normalized (without trailing slash)
        responses.add(
            responses.GET,
            f'https://mastodon.social/api/v1/statuses/{post_id}',
            json={
                'favourites_count': 50,
                'replies_count': 10,
                'reblogs_count': 5
            },
            status=200
        )

        metrics = fetch_mastodon_analytics(post_id, instance_url, access_token)
        assert metrics['likes'] == 50

    @responses.activate
    def test_fetch_mastodon_analytics_api_error(self):
        """Test Mastodon analytics fetch with API error."""
        post_id = '654321'
        instance_url = 'https://mastodon.social'
        access_token = 'test_token'

        # Mock API error
        responses.add(
            responses.GET,
            f'{instance_url}/api/v1/statuses/{post_id}',
            json={'error': 'Not found'},
            status=404
        )

        with pytest.raises(AnalyticsFetchError):
            fetch_mastodon_analytics(post_id, instance_url, access_token)


@pytest.mark.django_db
class TestFetchPixelfedAnalytics:
    """Tests for Pixelfed analytics fetching."""

    @responses.activate
    def test_fetch_pixelfed_analytics_success(self):
        """Test successful Pixelfed analytics fetch."""
        post_id = '111222'
        instance_url = 'https://pixelfed.social'
        access_token = 'test_token'

        # Mock Pixelfed API response
        responses.add(
            responses.GET,
            f'{instance_url}/api/v1/statuses/{post_id}',
            json={
                'favourites_count': 75,
                'replies_count': 15,
                'reblogs_count': 8
            },
            status=200
        )

        metrics = fetch_pixelfed_analytics(post_id, instance_url, access_token)

        assert metrics['likes'] == 75
        assert metrics['comments'] == 15
        assert metrics['shares'] == 8
        assert metrics['impressions'] is None
        assert metrics['reach'] is None
        assert metrics['saved'] == 0

    @responses.activate
    def test_fetch_pixelfed_analytics_with_shares_count(self):
        """Test Pixelfed analytics with shares_count field."""
        post_id = '111222'
        instance_url = 'https://pixelfed.social'
        access_token = 'test_token'

        # Mock response with shares_count
        responses.add(
            responses.GET,
            f'{instance_url}/api/v1/statuses/{post_id}',
            json={
                'favourites_count': 75,
                'replies_count': 15,
                'reblogs_count': 8,
                'shares_count': 12  # Pixelfed-specific field
            },
            status=200
        )

        metrics = fetch_pixelfed_analytics(post_id, instance_url, access_token)

        # Should use shares_count over reblogs_count
        assert metrics['shares'] == 12

    @responses.activate
    def test_fetch_pixelfed_analytics_api_error(self):
        """Test Pixelfed analytics fetch with API error."""
        post_id = '111222'
        instance_url = 'https://pixelfed.social'
        access_token = 'test_token'

        # Mock API error
        responses.add(
            responses.GET,
            f'{instance_url}/api/v1/statuses/{post_id}',
            json={'error': 'Unauthorized'},
            status=401
        )

        with pytest.raises(AnalyticsFetchError):
            fetch_pixelfed_analytics(post_id, instance_url, access_token)
