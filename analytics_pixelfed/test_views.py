"""
Tests for analytics_pixelfed views and templates.

These tests verify that the analytics dashboard and post detail pages
render correctly with the new templates.
"""

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client
from pixelfed.models import MastodonAccount


User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        email='test@example.com',
        password='testpass123',
        first_name='Test',
        last_name='User'
    )


@pytest.fixture
def client():
    """Create a test client."""
    return Client()


@pytest.fixture
def authenticated_client(client, user):
    """Create an authenticated test client."""
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestAnalyticsDashboard:
    """Tests for the analytics dashboard view."""

    def test_dashboard_redirects_to_pixelfed(self, authenticated_client):
        """Test that analytics dashboard redirects to pixelfed analytics."""
        url = reverse('analytics:dashboard')
        response = authenticated_client.get(url)
        
        # Should redirect to pixelfed analytics
        assert response.status_code == 302
        assert 'pixelfed' in response.url

    def test_pixelfed_dashboard_renders(self, authenticated_client):
        """Test that pixelfed analytics dashboard renders successfully."""
        url = reverse('analytics_pixelfed:dashboard')
        response = authenticated_client.get(url)
        
        # Should render successfully
        assert response.status_code == 200
        assert b'Analytics Dashboard' in response.content

    def test_dashboard_requires_login(self, client):
        """Test that analytics dashboard requires authentication."""
        url = reverse('analytics_pixelfed:dashboard')
        response = client.get(url)
        
        # Should redirect to login
        assert response.status_code == 302
        assert 'login' in response.url

    def test_dashboard_with_no_accounts(self, authenticated_client, user):
        """Test dashboard displays message when no accounts are connected."""
        url = reverse('analytics_pixelfed:dashboard')
        response = authenticated_client.get(url)
        
        assert response.status_code == 200
        assert b'No Pixelfed accounts connected' in response.content

    def test_dashboard_displays_connected_accounts(self, authenticated_client, user, db):
        """Test dashboard displays connected Pixelfed accounts."""
        # Create a test Pixelfed account
        account = MastodonAccount.objects.create(
            user=user,
            instance_url='https://pixelfed.social',
            username='testuser',
            access_token='test_token_123',
            account_id='123456'
        )
        
        url = reverse('analytics_pixelfed:dashboard')
        response = authenticated_client.get(url)
        
        assert response.status_code == 200
        assert b'@testuser' in response.content
        assert b'pixelfed.social' in response.content
