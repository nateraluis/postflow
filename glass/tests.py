from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from glass.models import GlassAccount, ManualPostTask
from glass.utils import complete_task, queue_manual_post, skip_task
from mastodon_native.models import MastodonAccount
from postflow.models import ScheduledPost


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(email="other@example.com", password="x")


@pytest.fixture
def glass_account(user):
    return GlassAccount.objects.create(user=user, username="ownerhandle")


def _make_post(user, **kwargs):
    return ScheduledPost.objects.create(
        user=user,
        caption="A test caption",
        post_date=timezone.now() + timedelta(hours=1),
        **kwargs,
    )


@pytest.fixture
def glass_only_post(user, glass_account):
    post = _make_post(user)
    post.glass_accounts.add(glass_account)
    return post


@pytest.fixture
def mixed_post(user, glass_account):
    mastodon_account = MastodonAccount.objects.create(
        user=user,
        instance_url="https://m.example",
        access_token="t",
        username="u",
    )
    post = _make_post(user)
    post.glass_accounts.add(glass_account)
    post.mastodon_native_accounts.add(mastodon_account)
    return post


@pytest.mark.django_db
class TestQueueManualPost:
    def test_glass_only_post_becomes_awaiting_manual(self, glass_only_post):
        task = queue_manual_post(glass_only_post)

        assert task.platform == "glass"
        assert task.status == "ready"
        assert task.ready_at is not None

        glass_only_post.refresh_from_db()
        assert glass_only_post.status == "awaiting_manual"

    def test_idempotent(self, glass_only_post):
        queue_manual_post(glass_only_post)
        queue_manual_post(glass_only_post)

        assert ManualPostTask.objects.filter(scheduled_post=glass_only_post).count() == 1

    def test_mixed_post_status_left_alone(self, mixed_post):
        queue_manual_post(mixed_post)

        mixed_post.refresh_from_db()
        assert mixed_post.status == "pending"
        # A manual task is still queued so the user has something to do for Glass.
        assert ManualPostTask.objects.filter(scheduled_post=mixed_post).exists()


@pytest.mark.django_db
class TestCompleteTask:
    def test_flips_awaiting_manual_post_to_posted(self, glass_only_post):
        task = queue_manual_post(glass_only_post)

        complete_task(task, posted_url="https://glass.photo/p/123")

        task.refresh_from_db()
        glass_only_post.refresh_from_db()
        assert task.status == "posted"
        assert task.posted_url == "https://glass.photo/p/123"
        assert task.completed_at is not None
        assert glass_only_post.status == "posted"

    def test_leaves_mixed_post_status_alone(self, mixed_post):
        task = queue_manual_post(mixed_post)

        complete_task(task)

        mixed_post.refresh_from_db()
        assert mixed_post.status == "pending"


@pytest.mark.django_db
class TestSkipTask:
    def test_skip_marks_awaiting_manual_post_deleted(self, glass_only_post):
        task = queue_manual_post(glass_only_post)

        skip_task(task)

        task.refresh_from_db()
        glass_only_post.refresh_from_db()
        assert task.status == "skipped"
        assert task.completed_at is not None
        assert glass_only_post.status == "deleted"


@pytest.mark.django_db
class TestViews:
    def test_mark_posted_completes_task(self, client, user, glass_only_post):
        task = queue_manual_post(glass_only_post)
        client.force_login(user)

        resp = client.post(
            f"/glass/tasks/{task.id}/done/",
            {"posted_url": "https://glass.photo/p/1"},
        )

        assert resp.status_code == 302
        task.refresh_from_db()
        assert task.status == "posted"
        assert task.posted_url == "https://glass.photo/p/1"

    def test_mark_posted_scoped_to_owner(self, client, other_user, glass_only_post):
        task = queue_manual_post(glass_only_post)
        client.force_login(other_user)

        resp = client.post(f"/glass/tasks/{task.id}/done/", {})

        assert resp.status_code == 404
        task.refresh_from_db()
        assert task.status == "ready"

    def test_skip_task_scoped_to_owner(self, client, other_user, glass_only_post):
        task = queue_manual_post(glass_only_post)
        client.force_login(other_user)

        resp = client.post(f"/glass/tasks/{task.id}/skip/", {})

        assert resp.status_code == 404
        task.refresh_from_db()
        assert task.status == "ready"

    def test_add_account_creates_account(self, client, user):
        client.force_login(user)

        resp = client.post("/glass/accounts/add/", {"username": "@newhandle"})

        assert resp.status_code == 302
        assert GlassAccount.objects.filter(user=user, username="newhandle").exists()

    def test_queue_renders(self, client, user, glass_only_post):
        queue_manual_post(glass_only_post)
        client.force_login(user)

        resp = client.get("/glass/")

        assert resp.status_code == 200
        assert b"Manual queue" in resp.content
