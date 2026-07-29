from datetime import timedelta
from unittest.mock import patch

import pytest
import responses
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from postflow.models import ScheduledPost
from threads.management.commands.refresh_threads_tokens import Command as RefreshCommand
from threads.models import ThreadsAccount
from threads.views import OAUTH_STATE_SESSION_KEY


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(email="other@example.com", password="x")


@pytest.fixture
def threads_account(user):
    return ThreadsAccount.objects.create(
        user=user,
        threads_user_id="1000",
        username="owner",
        access_token="old-token",
        expires_at=timezone.now() + timedelta(days=60),
    )


@pytest.fixture
def scheduled_post(user, threads_account):
    post = ScheduledPost.objects.create(
        user=user,
        caption="Hello from the test suite",
        post_date=timezone.now() + timedelta(hours=1),
        status="pending",
    )
    post.threads_accounts.add(threads_account)
    return post


@pytest.mark.django_db
class TestThreadsCallback:
    def test_state_mismatch_creates_no_account(self, client, user):
        client.force_login(user)
        session = client.session
        session[OAUTH_STATE_SESSION_KEY] = "expected-state"
        session.save()

        resp = client.get(
            reverse("threads:callback"),
            {"code": "auth-code", "state": "wrong-state"},
        )

        assert resp.status_code == 302
        assert ThreadsAccount.objects.count() == 0

    def test_missing_state_creates_no_account(self, client, user):
        client.force_login(user)
        # No state stashed in session at all.
        resp = client.get(reverse("threads:callback"), {"code": "auth-code"})

        assert resp.status_code == 302
        assert ThreadsAccount.objects.count() == 0

    @responses.activate
    def test_happy_path_creates_account_with_long_lived_token(self, client, user):
        client.force_login(user)
        session = client.session
        session[OAUTH_STATE_SESSION_KEY] = "matching-state"
        session.save()

        responses.add(
            responses.POST,
            "https://graph.threads.net/oauth/access_token",
            json={"access_token": "short-lived-token", "user_id": "123456"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://graph.threads.net/access_token",
            json={"access_token": "long-lived-token", "expires_in": 5184000},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://graph.threads.net/v1.0/me",
            json={"id": "123456", "username": "photographer"},
            status=200,
        )

        resp = client.get(
            reverse("threads:callback"),
            {"code": "auth-code", "state": "matching-state"},
        )

        assert resp.status_code == 302
        account = ThreadsAccount.objects.get(user=user, threads_user_id="123456")
        assert account.access_token == "long-lived-token"
        assert account.username == "photographer"
        assert account.expires_at > timezone.now() + timedelta(days=59)

        # State is single-use: replaying the same request should fail.
        resp2 = client.get(
            reverse("threads:callback"),
            {"code": "auth-code", "state": "matching-state"},
        )
        assert resp2.status_code == 302
        assert ThreadsAccount.objects.count() == 1


@pytest.mark.django_db
class TestPostThreads:
    @responses.activate
    def test_text_only_happy_path(self, scheduled_post, threads_account):
        from threads.utils import post_threads

        responses.add(
            responses.POST,
            "https://graph.threads.net/v1.0/1000/threads",
            json={"id": "container-1"},
            status=200,
        )
        responses.add(
            responses.POST,
            "https://graph.threads.net/v1.0/1000/threads_publish",
            json={"id": "post-1"},
            status=200,
        )

        post_threads(scheduled_post)

        scheduled_post.refresh_from_db()
        assert scheduled_post.status == "posted"
        assert scheduled_post.threads_post_id == "post-1"

    @responses.activate
    @patch("threads.utils.time.sleep", return_value=None)
    def test_publish_failure_marks_post_failed(self, mock_sleep, scheduled_post, threads_account):
        from threads.utils import post_threads

        responses.add(
            responses.POST,
            "https://graph.threads.net/v1.0/1000/threads",
            json={"id": "container-1"},
            status=200,
        )
        # Publish fails every attempt (retried MAX_PUBLISH_RETRIES times).
        for _ in range(3):
            responses.add(
                responses.POST,
                "https://graph.threads.net/v1.0/1000/threads_publish",
                json={"error": {"type": "OAuthException", "code": 500, "message": "server error"}},
                status=500,
            )

        post_threads(scheduled_post)

        scheduled_post.refresh_from_db()
        assert scheduled_post.status == "failed"
        assert not scheduled_post.threads_post_id


@pytest.mark.django_db
class TestRefreshThreadsTokens:
    @responses.activate
    def test_refreshes_expiring_token(self, threads_account):
        threads_account.expires_at = timezone.now() + timedelta(days=2)
        threads_account.access_token = "old-token"
        threads_account.save(update_fields=["expires_at", "access_token"])

        responses.add(
            responses.GET,
            "https://graph.threads.net/refresh_access_token",
            json={"access_token": "refreshed-token", "expires_in": 5184000},
            status=200,
        )

        RefreshCommand().handle()

        threads_account.refresh_from_db()
        assert threads_account.access_token == "refreshed-token"
        assert threads_account.expires_at > timezone.now() + timedelta(days=59)

    @responses.activate
    def test_skips_token_not_expiring_soon(self, threads_account):
        threads_account.expires_at = timezone.now() + timedelta(days=45)
        threads_account.access_token = "fresh-token"
        threads_account.save(update_fields=["expires_at", "access_token"])

        # No responses registered: a request here would raise ConnectionError.
        RefreshCommand().handle()

        threads_account.refresh_from_db()
        assert threads_account.access_token == "fresh-token"


@pytest.mark.django_db
class TestDisconnectThreads:
    def test_disconnect_scoped_to_owner(self, client, other_user, threads_account):
        client.force_login(other_user)

        resp = client.post(reverse("threads:disconnect", args=[threads_account.pk]))

        assert resp.status_code == 404
        assert ThreadsAccount.objects.filter(pk=threads_account.pk).exists()

    def test_owner_can_disconnect(self, client, user, threads_account):
        client.force_login(user)

        resp = client.post(reverse("threads:disconnect", args=[threads_account.pk]))

        assert resp.status_code == 302
        assert not ThreadsAccount.objects.filter(pk=threads_account.pk).exists()
