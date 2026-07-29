import json
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from analytics_site.collect import collect_website
from analytics_site.models import AnalyticsConnection, SiteSnapshot
from analytics_site.utils import get_post_impact, get_series
from postflow.models import ScheduledPost
from websites.models import Website


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def website(user):
    return Website.objects.create(user=user, url="https://example.com")


@pytest.mark.django_db
class TestCollectWebsite:
    def test_collects_active_connections_and_denormalises(self, website, monkeypatch):
        AnalyticsConnection.objects.create(
            website=website, provider="plausible", config={"api_key": "k", "site_id": "example.com"}
        )
        AnalyticsConnection.objects.create(
            website=website, provider="ghost_admin", config={"admin_api_key": "id:aa"}
        )

        monkeypatch.setattr(
            "analytics_site.providers.plausible.collect",
            lambda connection, date: {"aggregate": {"metrics": [10, 20, 30.0, 5.0, 12]}},
        )
        monkeypatch.setattr(
            "analytics_site.providers.ghost_admin.collect",
            lambda connection, date: {"growth": {"summary": {"total_members": 50}}},
        )

        date = timezone.now().date()
        snapshot, results = collect_website(website, date=date)

        assert results == {"plausible": "ok", "ghost_admin": "ok"}
        assert snapshot.visitors == 10
        assert snapshot.pageviews == 20
        assert snapshot.subscribers == 50
        assert snapshot.subscriber_delta is None  # no previous snapshot yet

        for connection in website.analytics_connections.all():
            assert connection.last_error == ""
            assert connection.last_collected_at is not None

    def test_subscriber_delta_uses_previous_snapshot(self, website, monkeypatch):
        AnalyticsConnection.objects.create(
            website=website, provider="ghost_admin", config={"admin_api_key": "id:aa"}
        )
        yesterday = timezone.now().date() - timedelta(days=1)
        SiteSnapshot.objects.create(website=website, date=yesterday, subscribers=40)

        monkeypatch.setattr(
            "analytics_site.providers.ghost_admin.collect",
            lambda connection, date: {"growth": {"summary": {"total_members": 45}}},
        )

        snapshot, _ = collect_website(website, date=timezone.now().date())
        assert snapshot.subscribers == 45
        assert snapshot.subscriber_delta == 5

    def test_one_provider_failure_does_not_block_others(self, website, monkeypatch):
        AnalyticsConnection.objects.create(
            website=website, provider="plausible", config={"api_key": "k", "site_id": "example.com"}
        )
        AnalyticsConnection.objects.create(
            website=website, provider="ghost_admin", config={"admin_api_key": "id:aa"}
        )

        def boom(connection, date):
            raise ValueError("plausible is down")

        monkeypatch.setattr("analytics_site.providers.plausible.collect", boom)
        monkeypatch.setattr(
            "analytics_site.providers.ghost_admin.collect",
            lambda connection, date: {"growth": {"summary": {"total_members": 12}}},
        )

        snapshot, results = collect_website(website, date=timezone.now().date())

        assert results["plausible"].startswith("error:")
        assert results["ghost_admin"] == "ok"
        assert snapshot.subscribers == 12

        plausible_conn = AnalyticsConnection.objects.get(website=website, provider="plausible")
        assert "plausible is down" in plausible_conn.last_error


@pytest.mark.django_db
class TestImportPhotoAnalytics:
    def _make_db(self, tmp_path):
        db_path = tmp_path / "analytics.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE snapshots (date TEXT PRIMARY KEY, days INTEGER, ghost TEXT, plausible TEXT, gsc TEXT, suggest TEXT)"
        )
        rows = [
            ("2026-06-01", 1, {"growth": {"summary": {"total_members": 90}}}, {"aggregate": {"metrics": [5, 8, 50.0, 30.0, 6]}}, {}, {}),
            ("2026-06-02", 1, {"growth": {"summary": {"total_members": 92}}}, {"aggregate": {"metrics": [7, 10, 40.0, 25.0, 8]}}, {}, {}),
            ("2026-06-03", 1, {"growth": {"summary": {"total_members": 95}}}, {"aggregate": {"metrics": [3, 4, 60.0, 20.0, 3]}}, {}, {}),
        ]
        for date, days, ghost, plausible, gsc, suggest in rows:
            conn.execute(
                "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?)",
                (date, days, json.dumps(ghost), json.dumps(plausible), json.dumps(gsc), json.dumps(suggest)),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_import_creates_snapshots_with_denormalised_fields_and_deltas(self, website, tmp_path):
        db_path = self._make_db(tmp_path)
        call_command("import_photo_analytics", website=website.id, file=str(db_path))

        snapshots = list(SiteSnapshot.objects.filter(website=website).order_by("date"))
        assert len(snapshots) == 3

        first, second, third = snapshots
        assert first.visitors == 5 and first.pageviews == 8 and first.subscribers == 90
        assert first.subscriber_delta is None

        assert second.subscribers == 92
        assert second.subscriber_delta == 2

        assert third.subscribers == 95
        assert third.subscriber_delta == 3

    def test_import_is_idempotent(self, website, tmp_path):
        db_path = self._make_db(tmp_path)
        call_command("import_photo_analytics", website=website.id, file=str(db_path))
        call_command("import_photo_analytics", website=website.id, file=str(db_path))
        assert SiteSnapshot.objects.filter(website=website).count() == 3


@pytest.mark.django_db
class TestGetPostImpact:
    def test_computes_lift_against_baseline(self, user, website):
        base_date = timezone.now().date() - timedelta(days=10)
        for offset, visitors in [(-3, 10), (-2, 10), (-1, 10), (0, 40), (1, 20)]:
            SiteSnapshot.objects.create(website=website, date=base_date + timedelta(days=offset), visitors=visitors)

        from mastodon_native.models import MastodonAccount

        account = MastodonAccount.objects.create(
            user=user, instance_url="https://mastodon.example", access_token="t", username="tester"
        )
        post = ScheduledPost.objects.create(
            user=user,
            caption="A post",
            post_date=timezone.make_aware(
                timezone.datetime.combine(base_date, timezone.datetime.min.time())
            ) + timedelta(hours=12),
            status="posted",
        )
        post.mastodon_native_accounts.add(account)

        results = get_post_impact(user, website, days=30)
        assert len(results) == 1
        row = results[0]
        assert row["platform"] == "mastodon"
        assert row["visitors_after"] == 60  # 40 + 20
        assert row["baseline"] == 10.0
        assert row["lift_pct"] == 200.0  # (60 - 20) / 20 * 100

    def test_ignores_posts_outside_window(self, user, website):
        old_post = ScheduledPost.objects.create(
            user=user,
            caption="Old",
            post_date=timezone.now() - timedelta(days=200),
            status="posted",
        )
        assert get_post_impact(user, website, days=30) == []

    def test_handles_missing_snapshots(self, user, website):
        post = ScheduledPost.objects.create(
            user=user,
            caption="No data around this",
            post_date=timezone.now() - timedelta(days=1),
            status="posted",
        )
        # No snapshots at all for this website -> gracefully skipped, no crash
        assert get_post_impact(user, website, days=30) == []


@pytest.mark.django_db
class TestGetSeries:
    def test_ascending_order(self, website):
        today = timezone.now().date()
        SiteSnapshot.objects.create(website=website, date=today, visitors=5)
        SiteSnapshot.objects.create(website=website, date=today - timedelta(days=1), visitors=3)

        series = get_series(website, days=30)
        assert [row["visitors"] for row in series] == [3, 5]


@pytest.mark.django_db
class TestViews:
    def test_dashboard_requires_login(self, client):
        resp = client.get("/analytics/site/")
        assert resp.status_code == 302

    def test_dashboard_scoped_to_owner(self, client, user, website):
        other = get_user_model().objects.create_user(email="other@example.com", password="x")
        client.force_login(other)
        resp = client.get(f"/analytics/site/?website={website.id}")
        assert resp.status_code == 404

    def test_dashboard_renders_for_owner(self, client, user, website):
        client.force_login(user)
        resp = client.get(f"/analytics/site/?website={website.id}")
        assert resp.status_code == 200
        assert b"Site Analytics" in resp.content

    def test_add_connection_creates_row(self, client, user, website):
        client.force_login(user)
        resp = client.post(
            f"/analytics/site/connections/{website.id}/add/",
            {"provider": "plausible", "api_key": "abc", "site_id": "example.com"},
        )
        assert resp.status_code == 302
        connection = AnalyticsConnection.objects.get(website=website, provider="plausible")
        assert connection.config == {"api_key": "abc", "site_id": "example.com"}

    def test_add_connection_scoped_to_owner(self, client, website):
        other = get_user_model().objects.create_user(email="other2@example.com", password="x")
        client.force_login(other)
        resp = client.post(
            f"/analytics/site/connections/{website.id}/add/",
            {"provider": "plausible", "api_key": "abc", "site_id": "example.com"},
        )
        assert resp.status_code == 404
        assert not AnalyticsConnection.objects.filter(website=website).exists()

    def test_delete_connection(self, client, user, website):
        connection = AnalyticsConnection.objects.create(
            website=website, provider="plausible", config={"api_key": "k", "site_id": "s"}
        )
        client.force_login(user)
        resp = client.post(f"/analytics/site/connections/{connection.id}/delete/")
        assert resp.status_code == 302
        assert not AnalyticsConnection.objects.filter(id=connection.id).exists()


@pytest.mark.django_db
class TestSEOOverview:
    def test_aggregates_queries_and_opportunities(self, website):
        from datetime import date, timedelta as td

        from analytics_site.utils import get_seo_overview

        today = date.today()
        for i, (clicks, imp) in enumerate([(2, 20), (1, 15)]):
            SiteSnapshot.objects.create(
                website=website,
                date=today - td(days=i),
                gsc={
                    "totals": {"clicks": clicks, "impressions": imp},
                    "queries": [
                        {"keys": ["amsterdam photography"], "clicks": clicks, "impressions": imp, "position": 8.0},
                        {"keys": ["street zine"], "clicks": 0, "impressions": 5, "position": 14.0},
                    ],
                    "pages": [
                        {"keys": ["https://example.com/a/"], "clicks": clicks, "impressions": imp, "position": 6.0},
                    ],
                },
            )

        seo = get_seo_overview(website, days=28)
        assert seo["has_data"]
        assert seo["totals"] == {"clicks": 3, "impressions": 35, "ctr": 8.6}
        top = seo["top_queries"][0]
        assert top["key"] == "amsterdam photography"
        assert top["clicks"] == 3 and top["impressions"] == 35
        assert top["position"] == 8.0
        # striking distance: decent impressions, position 4-25
        opp_keys = [o["key"] for o in seo["opportunities"]]
        assert "street zine" in opp_keys

    def test_no_data(self, website):
        from analytics_site.utils import get_seo_overview
        assert get_seo_overview(website)["has_data"] is False
