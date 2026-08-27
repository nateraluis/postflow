"""Tests for platform validation and text-only publishing fixes."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from mastodon_native.models import MastodonAccount as NativeMastodonAccount
from postflow.models import ScheduledPost
from postflow.payload import PostPayload


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.mark.django_db
class TestValidateForPlatform:
    def test_instagram_requires_image(self):
        assert any(
            "image" in e
            for e in PostPayload(caption="hi", image_count=0).validate_for_platform("instagram")
        )
        assert PostPayload(caption="hi", image_count=1).validate_for_platform("instagram") == []

    def test_instagram_counts_inline_hashtags(self):
        p = PostPayload(caption="hi #a #b #c #d #e #f", image_count=1)
        assert any("hashtags" in e for e in p.validate_for_platform("instagram"))
        ok = PostPayload(caption="hi #a #b", image_count=1)
        assert ok.validate_for_platform("instagram") == []

    def test_pixelfed_requires_image(self):
        assert any(
            "image" in e
            for e in PostPayload(caption="hi", image_count=0).validate_for_platform("pixelfed")
        )

    def test_glass_caption_limit_and_image(self):
        p = PostPayload(caption="x" * 601, image_count=0)
        errors = p.validate_for_platform("glass")
        assert any("Glass limit" in e for e in errors)
        assert any("image" in e for e in errors)

    def test_mastodon_text_only_is_valid(self):
        assert PostPayload(caption="hi", image_count=0).validate_for_platform("mastodon") == []


@pytest.mark.django_db
class TestTextOnlyMastodon:
    def test_posts_without_images(self, user):
        post = ScheduledPost.objects.create(
            user=user, caption="text only", post_date=timezone.now(), status="pending"
        )
        account = NativeMastodonAccount.objects.create(
            user=user, instance_url="https://hachyderm.io", access_token="t", username="m"
        )
        post.mastodon_native_accounts.add(account)

        with patch("mastodon_native.utils.Mastodon") as mock_masto:
            mock_masto.return_value.status_post.return_value = {"id": "123"}
            from mastodon_native.utils import post_mastodon

            post_mastodon(post, None)

        post.refresh_from_db()
        assert post.status == "posted"
        assert post.mastodon_post_id == "123"

    def test_no_caption_and_no_images_fails(self, user):
        post = ScheduledPost.objects.create(
            user=user, caption="", post_date=timezone.now(), status="pending"
        )
        account = NativeMastodonAccount.objects.create(
            user=user, instance_url="https://hachyderm.io", access_token="t", username="m"
        )
        post.mastodon_native_accounts.add(account)

        from mastodon_native.utils import post_mastodon

        post_mastodon(post, None)
        post.refresh_from_db()
        assert post.status == "failed"
