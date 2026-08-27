"""Tests for Pixelfed token lifetime handling and cross-platform failure masking.

Regression tests for the bug where an expired Pixelfed token made every
publish fail with an opaque 500 while a later Mastodon success overwrote
the post status back to "posted", hiding the failure entirely.
"""
import base64
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from mastodon_native.models import MastodonAccount as NativeMastodonAccount
from pixelfed.models import MastodonAccount
from pixelfed.tokens import ensure_fresh_token, token_expiry_from_jwt
from postflow.cron import publish_to_platforms
from postflow.models import ScheduledPost


def make_jwt(exp_ts):
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64({'typ': 'JWT'})}.{b64({'exp': exp_ts})}.sig"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def pixelfed_account(user):
    return MastodonAccount.objects.create(
        user=user,
        instance_url="https://pixelfed.social",
        access_token="opaque-token",
        username="tester",
    )


class TestTokenExpiry:
    def test_reads_exp_claim_from_jwt(self):
        exp = int((timezone.now() + timedelta(days=30)).timestamp())
        expiry = token_expiry_from_jwt(make_jwt(exp))
        assert int(expiry.timestamp()) == exp

    def test_opaque_token_has_no_expiry(self):
        assert token_expiry_from_jwt("not-a-jwt") is None


@pytest.mark.django_db
class TestEnsureFreshToken:
    def test_valid_token_passes(self, pixelfed_account):
        pixelfed_account.token_expires_at = timezone.now() + timedelta(days=200)
        assert ensure_fresh_token(pixelfed_account) is True

    def test_expired_token_without_refresh_fails(self, pixelfed_account):
        exp = int((timezone.now() - timedelta(days=10)).timestamp())
        pixelfed_account.access_token = make_jwt(exp)
        pixelfed_account.save()

        assert ensure_fresh_token(pixelfed_account) is False
        # expiry gets backfilled from the JWT so the failure is diagnosable
        pixelfed_account.refresh_from_db()
        assert pixelfed_account.token_expires_at is not None
        assert pixelfed_account.token_expires_at < timezone.now()

    def test_opaque_token_without_expiry_is_assumed_valid(self, pixelfed_account):
        assert ensure_fresh_token(pixelfed_account) is True

    def test_near_expiry_token_is_refreshed(self, pixelfed_account):
        pixelfed_account.token_expires_at = timezone.now() + timedelta(days=2)
        pixelfed_account.refresh_token = "refresh-me"
        pixelfed_account.client_id = "cid"
        pixelfed_account.client_secret = "csecret"
        pixelfed_account.save()

        response = MagicMock()
        response.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 365 * 24 * 3600,
        }
        with patch("pixelfed.tokens.requests.post", return_value=response) as post:
            assert ensure_fresh_token(pixelfed_account) is True

        assert post.call_args.kwargs["data"]["grant_type"] == "refresh_token"
        pixelfed_account.refresh_from_db()
        assert pixelfed_account.access_token == "new-token"
        assert pixelfed_account.refresh_token == "new-refresh"
        assert pixelfed_account.token_expires_at > timezone.now() + timedelta(days=300)


@pytest.mark.django_db
class TestFailureMasking:
    def _make_post(self, user):
        post = ScheduledPost.objects.create(
            user=user,
            caption="hello",
            post_date=timezone.now(),
            status="pending",
        )
        post.mastodon_accounts.add(
            MastodonAccount.objects.create(
                user=user,
                instance_url="https://pixelfed.social",
                access_token="t",
                username="pf",
            )
        )
        post.mastodon_native_accounts.add(
            NativeMastodonAccount.objects.create(
                user=user,
                instance_url="https://hachyderm.io",
                access_token="t",
                username="masto",
            )
        )
        return post

    def test_later_success_does_not_mask_earlier_failure(self, user):
        post = self._make_post(user)

        def fail_pixelfed(p, payload, in_reply_to_id=None):
            p.status = "failed"
            p.save(update_fields=["status"])

        def succeed_mastodon(p, payload, in_reply_to_id=None):
            p.status = "posted"
            p.save(update_fields=["status"])

        with patch("postflow.cron.post_pixelfed", side_effect=fail_pixelfed), \
             patch("postflow.cron.post_mastodon", side_effect=succeed_mastodon):
            failed = publish_to_platforms(post, payload=None)

        assert failed == ["pixelfed"]
        post.refresh_from_db()
        assert post.status == "failed"

    def test_all_platforms_succeeding_stays_posted(self, user):
        post = self._make_post(user)

        def succeed(p, payload, in_reply_to_id=None):
            p.status = "posted"
            p.save(update_fields=["status"])

        with patch("postflow.cron.post_pixelfed", side_effect=succeed), \
             patch("postflow.cron.post_mastodon", side_effect=succeed):
            failed = publish_to_platforms(post, payload=None)

        assert failed == []
        post.refresh_from_db()
        assert post.status == "posted"

    def test_platform_exception_marks_post_failed(self, user):
        post = self._make_post(user)

        def boom(p, payload, in_reply_to_id=None):
            raise RuntimeError("api down")

        def succeed(p, payload, in_reply_to_id=None):
            p.status = "posted"
            p.save(update_fields=["status"])

        with patch("postflow.cron.post_pixelfed", side_effect=boom), \
             patch("postflow.cron.post_mastodon", side_effect=succeed):
            failed = publish_to_platforms(post, payload=None)

        assert failed == ["pixelfed"]
        post.refresh_from_db()
        assert post.status == "failed"
