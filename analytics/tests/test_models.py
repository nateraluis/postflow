"""
Unit tests for analytics models using pytest.
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from analytics.models import PostAnalytics
from postflow.models import ScheduledPost, CustomUser


@pytest.fixture
def user(db):
    """Create a test user."""
    return CustomUser.objects.create_user(
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def scheduled_post(db, user):
    """Create a test scheduled post."""
    return ScheduledPost.objects.create(
        user=user,
        caption='Test post',
        post_date=timezone.now(),
        status='posted',
        instagram_post_id='123456',
        mastodon_post_id='654321',
        pixelfed_post_id='111222'
    )


@pytest.mark.django_db
class TestPostAnalyticsModel:
    """Tests for PostAnalytics model."""

    def test_create_post_analytics(self, scheduled_post):
        """Test creating a PostAnalytics instance."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456',
            likes=100,
            comments=20,
            shares=5
        )

        assert analytics.id is not None
        assert analytics.scheduled_post == scheduled_post
        assert analytics.platform == 'instagram'
        assert analytics.likes == 100
        assert analytics.comments == 20
        assert analytics.shares == 5

    def test_str_representation(self, scheduled_post):
        """Test string representation of PostAnalytics."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='mastodon',
            platform_post_id='654321'
        )

        expected = f"Mastodon analytics for post {scheduled_post.id}"
        assert str(analytics) == expected

    def test_total_engagement_property(self, scheduled_post):
        """Test total_engagement property calculation."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456',
            likes=100,
            comments=20,
            shares=5
        )

        assert analytics.total_engagement == 125

    def test_calculate_engagement_rate_with_impressions(self, scheduled_post):
        """Test engagement rate calculation with impressions."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456',
            likes=100,
            comments=20,
            shares=5,
            impressions=1000
        )

        # (100 + 20 + 5) / 1000 * 100 = 12.5%
        rate = analytics.calculate_engagement_rate()
        assert rate == Decimal('12.50')

    def test_calculate_engagement_rate_with_follower_count(self, scheduled_post):
        """Test engagement rate calculation with follower count."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='mastodon',
            platform_post_id='654321',
            likes=50,
            comments=10,
            shares=5
        )

        # (50 + 10 + 5) / 500 * 100 = 13%
        rate = analytics.calculate_engagement_rate(follower_count=500)
        assert rate == Decimal('13.00')

    def test_calculate_engagement_rate_no_data(self, scheduled_post):
        """Test engagement rate returns None when no data available."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='mastodon',
            platform_post_id='654321',
            likes=50,
            comments=10,
            shares=5
        )

        rate = analytics.calculate_engagement_rate()
        assert rate is None

    def test_auto_calculate_engagement_rate_on_save(self, scheduled_post):
        """Test that engagement rate is auto-calculated on save when impressions exist."""
        analytics = PostAnalytics(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456',
            likes=100,
            comments=20,
            shares=5,
            impressions=1000
        )
        analytics.save()

        assert analytics.engagement_rate == Decimal('12.50')

    def test_unique_together_constraint(self, scheduled_post):
        """Test unique_together constraint for post, platform, platform_post_id."""
        # Create first analytics record
        PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456'
        )

        # Attempt to create duplicate should raise error
        with pytest.raises(Exception):  # IntegrityError
            PostAnalytics.objects.create(
                scheduled_post=scheduled_post,
                platform='instagram',
                platform_post_id='123456'
            )

    def test_default_values(self, scheduled_post):
        """Test default values for analytics fields."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456'
        )

        assert analytics.likes == 0
        assert analytics.comments == 0
        assert analytics.shares == 0
        assert analytics.saved == 0
        assert analytics.impressions is None
        assert analytics.reach is None
        assert analytics.engagement_rate is None

    def test_ordering(self, scheduled_post):
        """Test that analytics are ordered by created_at descending."""
        # Create analytics at different times
        analytics1 = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='111'
        )

        analytics2 = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='mastodon',
            platform_post_id='222'
        )

        all_analytics = list(PostAnalytics.objects.all())
        # Should be ordered newest first
        assert all_analytics[0] == analytics2
        assert all_analytics[1] == analytics1

    def test_instagram_specific_fields(self, scheduled_post):
        """Test Instagram-specific fields (impressions, reach, saved)."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456',
            likes=100,
            impressions=2000,
            reach=1500,
            saved=50
        )

        assert analytics.impressions == 2000
        assert analytics.reach == 1500
        assert analytics.saved == 50

    def test_cascade_deletion(self, scheduled_post):
        """Test that analytics are deleted when post is deleted."""
        analytics = PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123456'
        )

        analytics_id = analytics.id
        scheduled_post.delete()

        assert not PostAnalytics.objects.filter(id=analytics_id).exists()
