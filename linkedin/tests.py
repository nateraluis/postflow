from datetime import timedelta

import pytest
import responses as responses_lib
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from linkedin.models import LinkedInAccount
from linkedin.utils import post_linkedin
from postflow.models import ScheduledPost

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(email="other@example.com", password="x")


@pytest.fixture
def linkedin_account(user):
    return LinkedInAccount.objects.create(
        user=user,
        member_urn="urn:li:person:abc123",
        username="Jane Doe",
        access_token="valid-token",
        expires_at=timezone.now() + timedelta(days=30),
    )


def _make_post(user, **kwargs):
    return ScheduledPost.objects.create(
        user=user,
        caption="A test caption",
        post_date=timezone.now() + timedelta(hours=1),
        **kwargs,
    )


@pytest.mark.django_db
class TestCallback:
    def test_state_mismatch_rejected(self, client, user):
        client.force_login(user)
        session = client.session
        session["linkedin_oauth_state"] = "expected-state"
        session.save()

        resp = client.get(reverse("linkedin:callback"), {"code": "abc", "state": "wrong-state"})

        assert resp.status_code == 302
        assert LinkedInAccount.objects.count() == 0

    @responses_lib.activate
    def test_happy_path_creates_account(self, client, user):
        client.force_login(user)
        session = client.session
        session["linkedin_oauth_state"] = "good-state"
        session.save()

        responses_lib.add(
            responses_lib.POST,
            TOKEN_URL,
            json={"access_token": "new-access-token", "expires_in": 5184000},
            status=200,
        )
        responses_lib.add(
            responses_lib.GET,
            USERINFO_URL,
            json={"sub": "member-42", "name": "Jane Doe"},
            status=200,
        )

        resp = client.get(reverse("linkedin:callback"), {"code": "abc", "state": "good-state"})

        assert resp.status_code == 302
        account = LinkedInAccount.objects.get(user=user)
        assert account.member_urn == "urn:li:person:member-42"
        assert account.username == "Jane Doe"
        assert account.access_token == "new-access-token"
        assert account.expires_at is not None
        assert account.expires_at > timezone.now()


@pytest.mark.django_db
class TestDisconnect:
    def test_scoped_to_owner(self, client, other_user, linkedin_account):
        client.force_login(other_user)

        resp = client.post(reverse("linkedin:disconnect", args=[linkedin_account.id]))

        assert resp.status_code == 404
        assert LinkedInAccount.objects.filter(id=linkedin_account.id).exists()

    def test_owner_can_disconnect(self, client, user, linkedin_account):
        client.force_login(user)

        resp = client.post(reverse("linkedin:disconnect", args=[linkedin_account.id]))

        assert resp.status_code == 302
        assert not LinkedInAccount.objects.filter(id=linkedin_account.id).exists()


@pytest.mark.django_db
class TestPostLinkedIn:
    @responses_lib.activate
    def test_text_only_happy_path(self, user, linkedin_account):
        post = _make_post(user)
        post.linkedin_accounts.add(linkedin_account)

        responses_lib.add(
            responses_lib.POST,
            POSTS_URL,
            status=201,
            headers={"x-restli-id": "urn:li:share:999"},
        )

        post_linkedin(post)

        post.refresh_from_db()
        assert post.status == "posted"
        assert post.linkedin_post_id == "urn:li:share:999"

    @responses_lib.activate
    def test_failure_marks_post_failed(self, user, linkedin_account):
        post = _make_post(user)
        post.linkedin_accounts.add(linkedin_account)

        responses_lib.add(
            responses_lib.POST,
            POSTS_URL,
            status=500,
            body="internal error",
        )

        post_linkedin(post)

        post.refresh_from_db()
        assert post.status == "failed"
        assert not post.linkedin_post_id

    @responses_lib.activate
    def test_expired_token_marks_post_failed_without_request(self, user):
        expired_account = LinkedInAccount.objects.create(
            user=user,
            member_urn="urn:li:person:expired",
            username="Old Token",
            access_token="stale-token",
            expires_at=timezone.now() - timedelta(days=1),
        )
        post = _make_post(user)
        post.linkedin_accounts.add(expired_account)

        post_linkedin(post)

        post.refresh_from_db()
        assert post.status == "failed"
        # No mocked responses registered, so a network call would raise —
        # reaching here proves the expired token short-circuited before any request.
