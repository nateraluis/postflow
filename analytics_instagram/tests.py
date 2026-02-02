"""
Tests for Instagram Analytics models and methods
"""
import pytest
from unittest.mock import Mock, patch
from django.conf import settings
from django.utils import timezone
from analytics_instagram.models import InstagramPost
from instagram.models import InstagramBusinessAccount
from postflow.models import CustomUser


@pytest.mark.django_db
class TestInstagramPostImageURL:
    """Tests for InstagramPost.get_display_image_url() method"""

    @pytest.fixture
    def user(self):
        """Create test user"""
        return CustomUser.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @pytest.fixture
    def instagram_account(self, user):
        """Create test Instagram Business account"""
        return InstagramBusinessAccount.objects.create(
            user=user,
            instagram_id='12345',
            username='testuser',
            access_token='test_token',
            expires_at=timezone.now() + timezone.timedelta(days=30)
        )

    @pytest.fixture
    def instagram_post(self, instagram_account):
        """Create test Instagram post"""
        return InstagramPost.objects.create(
            instagram_media_id='test_media_123',
            account=instagram_account,
            username='testuser',
            caption='Test post',
            media_url='https://instagram.com/test_image.jpg',
            media_type='IMAGE',
            permalink='https://instagram.com/p/test123',
            posted_at=timezone.now()
        )

    def test_get_display_image_url_without_cached_image(self, instagram_post):
        """Test that media_url is returned when cached_image is not set"""
        # ImageField with no file has name=None or name=''
        assert not instagram_post.cached_image
        url = instagram_post.get_display_image_url()
        assert url == 'https://instagram.com/test_image.jpg'

    @patch('analytics_instagram.models.settings')
    def test_get_display_image_url_with_cached_image_debug_mode(
        self, mock_settings, instagram_post
    ):
        """Test that cached_image.url is used in DEBUG mode"""
        mock_settings.DEBUG = True

        # Mock cached_image with url property
        instagram_post.cached_image = Mock()
        instagram_post.cached_image.name = 'analytics/instagram/2025/02/test.jpg'
        instagram_post.cached_image.url = '/media/analytics/instagram/2025/02/test.jpg'

        url = instagram_post.get_display_image_url()
        assert url == '/media/analytics/instagram/2025/02/test.jpg'

    def test_get_display_image_url_with_cached_image_production(self, instagram_post, settings):
        """Test that fresh signed URL is generated in production"""
        # Set production mode
        settings.DEBUG = False

        # Mock storage backend
        mock_storage = Mock()
        mock_storage.url.return_value = 'https://s3.amazonaws.com/bucket/test.jpg?signature=xyz'

        # Create a class-based mock that can be truthy and has storage attribute
        class MockImageField:
            def __init__(self):
                self.name = 'analytics/instagram/2025/02/test.jpg'
                self.storage = mock_storage
                self.url = '/media/fallback.jpg'

            def __bool__(self):
                return True

        instagram_post.cached_image = MockImageField()

        url = instagram_post.get_display_image_url()

        # Verify storage.url() was called with the file name
        mock_storage.url.assert_called_once_with('analytics/instagram/2025/02/test.jpg')
        assert 'signature=xyz' in url
        assert url.startswith('https://s3.amazonaws.com/')

    @patch('analytics_instagram.models.settings')
    def test_get_display_image_url_fallback_on_error(
        self, mock_settings, instagram_post
    ):
        """Test that method falls back to .url property if storage.url() fails"""
        mock_settings.DEBUG = False

        # Mock storage backend that raises exception
        mock_storage = Mock()
        mock_storage.url.side_effect = Exception('S3 error')

        # Mock cached_image
        instagram_post.cached_image = Mock()
        instagram_post.cached_image.name = 'analytics/instagram/2025/02/test.jpg'
        instagram_post.cached_image.storage = mock_storage
        instagram_post.cached_image.url = '/media/fallback.jpg'

        # Should fall back to .url property
        url = instagram_post.get_display_image_url()
        assert url == '/media/fallback.jpg'
