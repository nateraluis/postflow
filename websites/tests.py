from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from websites.models import BlogPost, ContentSource, Website
from websites.sources.base import SourceImage, SourcePost
from websites.sync import SyncError, sync_website


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def website(user):
    return Website.objects.create(user=user, url="https://example.com")


def _source_post(guid="p1", **overrides):
    defaults = dict(
        guid=guid,
        url=f"https://example.com/{guid}/",
        title=f"Post {guid}",
        slug=guid,
        excerpt="An excerpt",
        html_body="<p>Hello</p>",
        markdown_body="Hello",
        tags=["photography"],
        published_at=datetime(2026, 5, 1, tzinfo=dt_timezone.utc),
        images=[SourceImage(url=f"https://example.com/img-{guid}.jpg", is_feature=True)],
    )
    defaults.update(overrides)
    return SourcePost(**defaults)


class FakeAdapter:
    def __init__(self, posts):
        self._posts = posts

    def fetch_posts(self):
        yield from self._posts


@pytest.mark.django_db
class TestBestSource:
    def test_lowest_priority_active_wins(self, website):
        ContentSource.objects.create(website=website, kind="rss", priority=30)
        api = ContentSource.objects.create(
            website=website, kind="ghost_content_api", priority=10, is_active=False
        )
        assert website.best_source.kind == "rss"
        api.is_active = True
        api.save()
        assert website.best_source.kind == "ghost_content_api"

    def test_no_source(self, website):
        assert website.best_source is None


@pytest.mark.django_db
class TestSyncWebsite:
    def test_no_active_source_marks_error(self, website):
        with pytest.raises(SyncError):
            sync_website(website)
        website.refresh_from_db()
        assert website.sync_status == "error"

    @patch("websites.sync._download_image", return_value=None)
    @patch("websites.sync.build_adapter")
    def test_sync_creates_and_is_idempotent(self, mock_build, _mock_dl, website):
        ContentSource.objects.create(website=website, kind="rss", priority=30)
        mock_build.side_effect = lambda *a, **kw: FakeAdapter(
            [_source_post("p1"), _source_post("p2")]
        )

        created, updated = sync_website(website)
        assert (created, updated) == (2, 0)

        created, updated = sync_website(website)
        assert (created, updated) == (0, 2)
        assert website.posts.count() == 2

        website.refresh_from_db()
        assert website.sync_status == "ok"
        assert website.last_synced_at is not None

        post = website.posts.get(source_guid="p1")
        assert post.title == "Post p1"
        assert post.images.count() == 1
        assert post.images.first().is_feature

    @patch("websites.sync._download_image", return_value=None)
    @patch("websites.sync.build_adapter")
    def test_lower_fidelity_resync_does_not_blank_fields(self, mock_build, _mock_dl, website):
        ContentSource.objects.create(website=website, kind="rss", priority=30)
        rich = _source_post("p1")
        poor = _source_post("p1", markdown_body="", html_body="", excerpt="")
        mock_build.side_effect = [FakeAdapter([rich]), FakeAdapter([poor])]

        sync_website(website)
        sync_website(website)

        post = website.posts.get(source_guid="p1")
        assert post.markdown_body == "Hello"
        assert post.html_body == "<p>Hello</p>"

    @patch("websites.sync._download_image", return_value=None)
    @patch("websites.sync.build_adapter")
    def test_adapter_failure_marks_error(self, mock_build, _mock_dl, website):
        ContentSource.objects.create(website=website, kind="rss", priority=30)

        class BrokenAdapter:
            def fetch_posts(self):
                raise RuntimeError("boom")
                yield  # pragma: no cover

        mock_build.return_value = BrokenAdapter()
        with pytest.raises(RuntimeError):
            sync_website(website)
        website.refresh_from_db()
        assert website.sync_status == "error"
        assert "boom" in website.sync_error


class TestSSRFGuard:
    def test_private_hosts_rejected(self):
        from websites.sources.base import UnsafeURLError, validate_public_url

        for url in [
            "http://127.0.0.1/",
            "http://localhost:8000/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "ftp://example.com/",
            "file:///etc/passwd",
        ]:
            with pytest.raises(UnsafeURLError):
                validate_public_url(url)

    def test_redirect_does_not_duplicate_params(self, monkeypatch):
        import responses as responses_lib

        import websites.sources.base as base

        monkeypatch.setattr(base, "validate_public_url", lambda url: None)
        with responses_lib.RequestsMock() as rsps:
            rsps.get(
                "https://apex.example/api",
                status=301,
                headers={"Location": "https://www.apex.example/api?key=abc&limit=50"},
            )
            rsps.get(
                "https://www.apex.example/api",
                status=302,
                headers={"Location": "https://backend.example/api?key=abc&limit=50"},
            )
            rsps.get("https://backend.example/api", json={"ok": True})

            resp = base.make_session().get(
                "https://apex.example/api", params={"key": "abc", "limit": 50}
            )
            assert resp.json() == {"ok": True}
            final_url = rsps.calls[-1].request.url
            assert final_url.count("key=abc") == 1
            assert final_url.count("limit=50") == 1

    def test_session_blocks_private_redirect(self, monkeypatch):
        import responses as responses_lib

        import websites.sources.base as base

        original = base.validate_public_url
        monkeypatch.setattr(
            base,
            "validate_public_url",
            lambda url: None if "public.example" in url else original(url),
        )
        with responses_lib.RequestsMock() as rsps:
            rsps.get(
                "https://public.example/feed",
                status=302,
                headers={"Location": "http://169.254.169.254/latest/meta-data/"},
            )
            with pytest.raises(base.UnsafeURLError):
                base.make_session().get("https://public.example/feed")


@pytest.mark.django_db
class TestViews:
    def test_add_website_detects_sources(self, client, user):
        client.force_login(user)
        detected = [
            ("ghost_content_api", {}, 10),
            ("rss", {"feed_url": "https://example.com/rss/"}, 30),
        ]
        with patch("websites.views.detect_sources", return_value=detected), patch(
            "websites.views._fetch_site_title", return_value="Example"
        ):
            resp = client.post("/websites/add/", {"url": "example.com"})
        assert resp.status_code == 302

        website = Website.objects.get(user=user)
        assert website.url == "https://example.com"
        assert website.detected_platform == "ghost"
        kinds = dict(website.sources.values_list("kind", "is_active"))
        # Content API needs a key before it can be active
        assert kinds == {"ghost_content_api": False, "rss": True}

    def test_add_website_nothing_detected(self, client, user):
        client.force_login(user)
        with patch("websites.views.detect_sources", return_value=[]):
            client.post("/websites/add/", {"url": "https://nothing.example"})
        assert not Website.objects.filter(user=user).exists()

    def test_detail_scoped_to_owner(self, client, user, website):
        other = get_user_model().objects.create_user(email="other@example.com", password="x")
        client.force_login(other)
        assert client.get(f"/websites/{website.id}/").status_code == 404

    def test_list_renders(self, client, user, website):
        client.force_login(user)
        BlogPost.objects.create(
            website=website, source_guid="g", title="T", url="https://example.com/t/"
        )
        resp = client.get("/websites/")
        assert resp.status_code == 200
