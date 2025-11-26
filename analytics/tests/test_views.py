"""
Unit tests for analytics views using pytest.
"""
import pytest
from django.urls import reverse
from django.utils import timezone

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
def other_user(db):
    """Create another test user."""
    return CustomUser.objects.create_user(
        email='other@example.com',
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
        instagram_post_id='123456'
    )


@pytest.fixture
def post_with_analytics(db, scheduled_post):
    """Create a post with analytics."""
    analytics = PostAnalytics.objects.create(
        scheduled_post=scheduled_post,
        platform='instagram',
        platform_post_id='123456',
        likes=100,
        comments=20,
        shares=5,
        impressions=1000
    )
    return scheduled_post, analytics


@pytest.mark.django_db
class TestAnalyticsDashboardView:
    """Tests for analytics dashboard view."""

    def test_dashboard_requires_login(self, client):
        """Test that dashboard requires authentication."""
        url = reverse('analytics:dashboard')
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.url

    def test_dashboard_accessible_when_logged_in(self, client, user):
        """Test that dashboard is accessible for logged-in users."""
        client.force_login(user)
        url = reverse('analytics:dashboard')
        response = client.get(url)

        assert response.status_code == 200
        assert 'analytics/dashboard.html' in [t.name for t in response.templates]

    def test_dashboard_shows_user_posts_only(self, client, user, other_user, scheduled_post):
        """Test that dashboard only shows current user's posts."""
        # Create post for other user
        other_post = ScheduledPost.objects.create(
            user=other_user,
            caption='Other user post',
            post_date=timezone.now(),
            status='posted'
        )

        client.force_login(user)
        url = reverse('analytics:dashboard')
        response = client.get(url)

        assert response.status_code == 200
        posts = response.context['posts']

        # Should only see own post
        assert scheduled_post in posts
        assert other_post not in posts

    def test_dashboard_shows_only_posted_posts(self, client, user, scheduled_post):
        """Test that dashboard only shows posts with status='posted'."""
        # Create pending post
        pending_post = ScheduledPost.objects.create(
            user=user,
            caption='Pending post',
            post_date=timezone.now(),
            status='pending'
        )

        client.force_login(user)
        url = reverse('analytics:dashboard')
        response = client.get(url)

        posts = response.context['posts']
        assert scheduled_post in posts
        assert pending_post not in posts

    def test_dashboard_with_analytics(self, client, user, post_with_analytics):
        """Test dashboard displays analytics for posts."""
        post, analytics = post_with_analytics

        client.force_login(user)
        url = reverse('analytics:dashboard')
        response = client.get(url)

        assert response.status_code == 200
        posts = response.context['posts']

        # Verify post and analytics are present
        assert post in posts
        post_analytics = post.analytics.all()
        assert analytics in post_analytics

    def test_dashboard_platform_filter(self, client, user, scheduled_post):
        """Test platform filtering on dashboard."""
        # Create analytics for different platforms
        PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='instagram',
            platform_post_id='123',
            likes=100
        )
        PostAnalytics.objects.create(
            scheduled_post=scheduled_post,
            platform='mastodon',
            platform_post_id='456',
            likes=50
        )

        client.force_login(user)
        url = reverse('analytics:dashboard') + '?platform=instagram'
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['platform_filter'] == 'instagram'

    def test_dashboard_empty_state(self, client, user):
        """Test dashboard empty state when no posts."""
        client.force_login(user)
        url = reverse('analytics:dashboard')
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['total_posts'] == 0

    def test_dashboard_htmx_request(self, client, user):
        """Test HTMX request returns same template."""
        client.force_login(user)
        url = reverse('analytics:dashboard')
        response = client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        assert 'analytics/dashboard.html' in [t.name for t in response.templates]


@pytest.mark.django_db
class TestRefreshAnalyticsView:
    """Tests for refresh analytics view."""

    def test_refresh_requires_login(self, client):
        """Test that refresh requires authentication."""
        url = reverse('analytics:refresh')
        response = client.post(url)

        # Should redirect to login
        assert response.status_code == 302

    def test_refresh_requires_post_method(self, client, user):
        """Test that refresh only accepts POST requests."""
        client.force_login(user)
        url = reverse('analytics:refresh')
        response = client.get(url)

        # Should return 405 Method Not Allowed
        assert response.status_code == 405

    def test_refresh_all_posts(self, client, user, scheduled_post, mocker):
        """Test refreshing analytics for all posts."""
        # Mock call_command to avoid actual API calls
        mock_call_command = mocker.patch('analytics.views.call_command')

        client.force_login(user)
        url = reverse('analytics:refresh')
        response = client.post(url)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert 'recent posts' in data['message']

        # Verify command was called
        mock_call_command.assert_called_once_with('fetch_analytics', days=7, force=True)

    def test_refresh_specific_post(self, client, user, scheduled_post, mocker):
        """Test refreshing analytics for a specific post."""
        mock_call_command = mocker.patch('analytics.views.call_command')

        client.force_login(user)
        url = reverse('analytics:refresh')
        response = client.post(url, {'post_id': scheduled_post.id})

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert f'post {scheduled_post.id}' in data['message']

        mock_call_command.assert_called_once_with(
            'fetch_analytics',
            post_id=str(scheduled_post.id),
            force=True
        )

    def test_refresh_nonexistent_post(self, client, user, mocker):
        """Test refreshing analytics for non-existent post returns 404."""
        mocker.patch('analytics.views.call_command')

        client.force_login(user)
        url = reverse('analytics:refresh')
        response = client.post(url, {'post_id': 99999})

        assert response.status_code == 404

    def test_refresh_other_user_post(self, client, user, other_user, mocker):
        """Test that user cannot refresh other user's post."""
        mocker.patch('analytics.views.call_command')

        other_post = ScheduledPost.objects.create(
            user=other_user,
            caption='Other post',
            post_date=timezone.now(),
            status='posted'
        )

        client.force_login(user)
        url = reverse('analytics:refresh')
        response = client.post(url, {'post_id': other_post.id})

        # Should return 404 (not found for this user)
        assert response.status_code == 404


@pytest.mark.django_db
class TestPostDetailView:
    """Tests for post detail view."""

    def test_post_detail_requires_login(self, client, scheduled_post):
        """Test that post detail requires authentication."""
        url = reverse('analytics:post_detail', args=[scheduled_post.id])
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.url

    def test_post_detail_accessible_when_logged_in(self, client, user, scheduled_post):
        """Test post detail is accessible for post owner."""
        client.force_login(user)
        url = reverse('analytics:post_detail', args=[scheduled_post.id])
        response = client.get(url)

        assert response.status_code == 200
        assert 'analytics/post_detail.html' in [t.name for t in response.templates]

    def test_post_detail_shows_analytics(self, client, user, post_with_analytics):
        """Test that post detail shows analytics."""
        post, analytics = post_with_analytics

        client.force_login(user)
        url = reverse('analytics:post_detail', args=[post.id])
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['post'] == post
        assert analytics in response.context['analytics']

    def test_post_detail_other_user_post(self, client, user, other_user):
        """Test that user cannot view other user's post detail."""
        other_post = ScheduledPost.objects.create(
            user=other_user,
            caption='Other post',
            post_date=timezone.now(),
            status='posted'
        )

        client.force_login(user)
        url = reverse('analytics:post_detail', args=[other_post.id])
        response = client.get(url)

        # Should return 404
        assert response.status_code == 404

    def test_post_detail_nonexistent_post(self, client, user):
        """Test post detail with non-existent post ID."""
        client.force_login(user)
        url = reverse('analytics:post_detail', args=[99999])
        response = client.get(url)

        assert response.status_code == 404

    def test_post_detail_htmx_request(self, client, user, scheduled_post):
        """Test HTMX request returns same template."""
        client.force_login(user)
        url = reverse('analytics:post_detail', args=[scheduled_post.id])
        response = client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        assert 'analytics/post_detail.html' in [t.name for t in response.templates]
