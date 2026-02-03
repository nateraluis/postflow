"""
Tests for Pixelfed Analytics engagement distribution.
"""
import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from postflow.models import CustomUser
from pixelfed.models import MastodonAccount
from analytics_pixelfed.models import (
    PixelfedPost,
    PixelfedLike,
    PixelfedComment,
    PixelfedShare,
    PixelfedEngagementSummary,
)


@pytest.fixture
def user(db):
    """Create test user."""
    return CustomUser.objects.create_user(
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def pixelfed_account(user):
    """Create test Pixelfed account."""
    return MastodonAccount.objects.create(
        user=user,
        instance_url='https://pixelfed.social',
        username='testuser',
        access_token='test_token_123'
    )


@pytest.fixture
def pixelfed_post(pixelfed_account):
    """Create test Pixelfed post."""
    return PixelfedPost.objects.create(
        account=pixelfed_account,
        pixelfed_post_id='post123',
        instance_url='https://pixelfed.social',
        username='testuser',
        caption='Test post',
        media_url='https://example.com/image.jpg',
        post_url='https://pixelfed.social/@testuser/post123',
        posted_at=timezone.now()
    )


@pytest.fixture
def engagement_summary(pixelfed_post):
    """Create engagement summary with balanced engagement."""
    # Use update_or_create to avoid unique constraint violations
    summary, _ = PixelfedEngagementSummary.objects.update_or_create(
        post=pixelfed_post,
        defaults={
            'total_likes': 100,
            'total_comments': 50,
            'total_shares': 25,
            'total_engagement': 175
        }
    )
    return summary


@pytest.mark.django_db
class TestEngagementDistributionView:
    """Test engagement distribution view."""

    def test_view_requires_authentication(self, client):
        """Test that view requires login."""
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)
        assert response.status_code == 302  # Redirect to login
        assert '/login/' in response.url

    def test_view_accessible_when_authenticated(self, client, user):
        """Test authenticated users can access view."""
        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)
        assert response.status_code == 200

    def test_view_uses_correct_template(self, client, user):
        """Test view uses shared template."""
        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)
        assert 'analytics/shared/engagement_distribution.html' in [
            t.name for t in response.templates
        ]

    def test_view_shows_engagement_distribution(self, client, user, pixelfed_account, engagement_summary):
        """Test view calculates and displays engagement distribution."""
        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)

        # Check context data
        assert 'total_likes' in response.context
        assert 'total_comments' in response.context
        assert 'total_shares' in response.context
        assert 'total_engagement' in response.context

        # Verify calculations
        assert response.context['total_likes'] == 100
        assert response.context['total_comments'] == 50
        assert response.context['total_shares'] == 25
        assert response.context['total_engagement'] == 175

    def test_view_calculates_percentages(self, client, user, pixelfed_account, engagement_summary):
        """Test view calculates correct percentages."""
        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)

        # Check percentages (100 likes, 50 comments, 25 shares out of 175 total)
        assert 'likes_percentage' in response.context
        assert 'comments_percentage' in response.context
        assert 'shares_percentage' in response.context

        # Verify percentage calculations
        assert abs(response.context['likes_percentage'] - 57.14) < 0.1  # 100/175 = 57.14%
        assert abs(response.context['comments_percentage'] - 28.57) < 0.1  # 50/175 = 28.57%
        assert abs(response.context['shares_percentage'] - 14.29) < 0.1  # 25/175 = 14.29%

    def test_view_handles_no_engagement_data(self, client, user, pixelfed_account):
        """Test view handles case with no engagement data."""
        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['total_engagement'] == 0

    def test_view_handles_zero_division(self, client, user, pixelfed_account, pixelfed_post):
        """Test view handles zero engagement gracefully."""
        # Create summary with all zeros using update_or_create
        PixelfedEngagementSummary.objects.update_or_create(
            post=pixelfed_post,
            defaults={
                'total_likes': 0,
                'total_comments': 0,
                'total_shares': 0,
                'total_engagement': 0
            }
        )

        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['likes_percentage'] == 0
        assert response.context['comments_percentage'] == 0
        assert response.context['shares_percentage'] == 0

    def test_view_aggregates_multiple_posts(self, client, user, pixelfed_account):
        """Test view aggregates engagement from multiple posts."""
        # Create multiple posts with engagement
        post1 = PixelfedPost.objects.create(
            account=pixelfed_account,
            pixelfed_post_id='post1',
            instance_url='https://pixelfed.social',
            username='testuser',
            post_url='https://pixelfed.social/@testuser/post1',
            posted_at=timezone.now()
        )
        PixelfedEngagementSummary.objects.update_or_create(
            post=post1,
            defaults={
                'total_likes': 50,
                'total_comments': 30,
                'total_shares': 20,
                'total_engagement': 100
            }
        )

        post2 = PixelfedPost.objects.create(
            account=pixelfed_account,
            pixelfed_post_id='post2',
            instance_url='https://pixelfed.social',
            username='testuser',
            post_url='https://pixelfed.social/@testuser/post2',
            posted_at=timezone.now()
        )
        PixelfedEngagementSummary.objects.update_or_create(
            post=post2,
            defaults={
                'total_likes': 30,
                'total_comments': 20,
                'total_shares': 10,
                'total_engagement': 60
            }
        )

        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)

        # Should aggregate: 80 likes, 50 comments, 30 shares
        assert response.context['total_likes'] == 80
        assert response.context['total_comments'] == 50
        assert response.context['total_shares'] == 30
        assert response.context['total_engagement'] == 160

    def test_view_only_shows_user_posts(self, client, user, pixelfed_account, engagement_summary):
        """Test view only shows posts from user's accounts."""
        # Create another user's account and post
        other_user = CustomUser.objects.create_user(
            email='other@example.com',
            password='otherpass123'
        )
        other_account = MastodonAccount.objects.create(
            user=other_user,
            instance_url='https://pixelfed.social',
            username='otheruser',
            access_token='other_token'
        )
        other_post = PixelfedPost.objects.create(
            account=other_account,
            pixelfed_post_id='otherpost',
            instance_url='https://pixelfed.social',
            username='otheruser',
            post_url='https://pixelfed.social/@otheruser/otherpost',
            posted_at=timezone.now()
        )
        PixelfedEngagementSummary.objects.update_or_create(
            post=other_post,
            defaults={
                'total_likes': 500,
                'total_comments': 300,
                'total_shares': 200
            }
        )

        client.force_login(user)
        url = reverse('analytics_pixelfed:engagement_distribution')
        response = client.get(url)

        # Should only show engagement from user's posts, not other user's
        assert response.context['total_likes'] == 100  # From engagement_summary fixture
        assert response.context['total_comments'] == 50
        assert response.context['total_shares'] == 25
