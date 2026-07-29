from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from campaigns.ai import DraftBatch, PlatformDraft, generate_drafts, get_voice_profile
from campaigns.models import Campaign, GeneratedDraft
from campaigns.utm import tag_url
from postflow.models import ScheduledPost
from websites.models import BlogPost, Website


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def blog_post(user):
    website = Website.objects.create(user=user, url="https://example.com")
    return BlogPost.objects.create(
        website=website,
        source_guid="p1",
        title="Walking Amsterdam",
        slug="walking-amsterdam",
        url="https://example.com/walking-amsterdam/",
        markdown_body="I walked the canals. The light was flat but honest.",
    )


@pytest.fixture
def campaign(user, blog_post):
    return Campaign.objects.create(
        user=user,
        website=blog_post.website,
        blog_post=blog_post,
        name="Promote: Walking Amsterdam",
        utm_campaign="walking-amsterdam-20260729",
    )


class TestUTM:
    def test_tag_url(self):
        url = tag_url("https://example.com/post/", "mastodon", "camp-1")
        assert "utm_source=mastodon" in url
        assert "utm_medium=social" in url
        assert "utm_campaign=camp-1" in url

    def test_tag_url_preserves_existing_params(self):
        url = tag_url("https://example.com/post/?ref=abc", "linkedin", "c")
        assert "ref=abc" in url
        assert "utm_source=linkedin" in url


@pytest.mark.django_db
class TestVoiceProfile:
    def test_seeded_from_default_file(self, user):
        profile = get_voice_profile(user)
        assert "em dashes" in profile.rules
        assert "British spelling" in profile.rules
        # Second call reuses the same profile
        assert get_voice_profile(user).id == profile.id


def _fake_parse_response(platforms):
    response = MagicMock()
    response.parsed_output = DraftBatch(
        drafts=[
            PlatformDraft(
                platform=p,
                caption=f"A caption for {p} — with a dash",
                hashtags=["photography"],
                image_indices=[],
            )
            for p in platforms
        ]
    )
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    return response


@pytest.mark.django_db
class TestGenerateDrafts:
    @patch("campaigns.ai.anthropic.Anthropic")
    def test_creates_draft_posts(self, mock_anthropic, campaign):
        mock_anthropic.return_value.messages.parse.return_value = _fake_parse_response(
            ["mastodon", "pixelfed"]
        )
        slots = [timezone.now() + timedelta(days=1), timezone.now() + timedelta(days=2)]

        results = generate_drafts(campaign, ["mastodon", "pixelfed"], slots)

        assert len(results) == 2
        for post, generated in results:
            assert post.status == "draft"  # approval invariant
            assert "—" not in post.caption  # hard rule enforced
            assert "#photography" in post.caption
            assert generated.campaign == campaign

    @patch("campaigns.ai.anthropic.Anthropic")
    def test_skips_platforms_not_requested(self, mock_anthropic, campaign):
        mock_anthropic.return_value.messages.parse.return_value = _fake_parse_response(
            ["mastodon", "linkedin"]
        )
        results = generate_drafts(campaign, ["mastodon"], [timezone.now() + timedelta(days=1)])
        assert [g.platform for _, g in results] == ["mastodon"]


@pytest.mark.django_db
class TestEvaluator:
    @patch("campaigns.evaluator.anthropic.Anthropic")
    def test_generates_weekly_report(self, mock_anthropic, user, blog_post):
        from campaigns.evaluator import Recommendation, ReportOutput, generate_report
        from campaigns.models import CampaignReport

        response = MagicMock()
        response.parsed_output = ReportOutput(
            report_markdown="A quiet week. Visitors held steady.",
            recommendations=[
                Recommendation(
                    type="evergreen",
                    platform="mastodon",
                    blog_post_id=blog_post.id,
                    rationale="This post has never been promoted.",
                )
            ],
        )
        response.usage.input_tokens = 500
        response.usage.output_tokens = 200
        mock_anthropic.return_value.messages.parse.return_value = response

        report = generate_report(user)

        assert CampaignReport.objects.count() == 1
        assert report.recommendations[0]["platform"] == "mastodon"
        assert "quiet week" in report.report_markdown

        # Re-running the same week replaces, not duplicates
        generate_report(user, week_start=report.week_start)
        assert CampaignReport.objects.count() == 1

    def test_report_views_scoped(self, client, user, blog_post):
        from campaigns.models import CampaignReport

        report = CampaignReport.objects.create(
            user=user,
            website=blog_post.website,
            week_start=timezone.now().date(),
            report_markdown="Report body",
            recommendations=[{"type": "other", "platform": "all", "rationale": "r"}],
        )
        client.force_login(user)
        assert client.get("/campaigns/reports/").status_code == 200
        assert client.get(f"/campaigns/reports/{report.id}/").status_code == 200

        other = get_user_model().objects.create_user(email="o2@example.com", password="x")
        client.force_login(other)
        assert client.get(f"/campaigns/reports/{report.id}/").status_code == 404


@pytest.mark.django_db
class TestReviewQueueFlow:
    def _make_draft(self, campaign, with_account=True):
        post = ScheduledPost.objects.create(
            user=campaign.user,
            caption="Draft caption",
            post_date=timezone.now() + timedelta(days=1),
            status="draft",
        )
        if with_account:
            from mastodon_native.models import MastodonAccount

            account = MastodonAccount.objects.create(
                user=campaign.user,
                instance_url="https://mastodon.example",
                access_token="t",
                username="tester",
            )
            post.mastodon_native_accounts.add(account)
        return GeneratedDraft.objects.create(
            campaign=campaign, scheduled_post=post, platform="mastodon", model_used="test"
        )

    def test_approve_sets_pending_and_marks_promoted(self, client, campaign):
        draft = self._make_draft(campaign)
        client.force_login(campaign.user)

        resp = client.post(
            f"/campaigns/drafts/{draft.id}/approve/", {"caption": "Edited caption"}
        )
        assert resp.status_code == 302

        draft.scheduled_post.refresh_from_db()
        assert draft.scheduled_post.status == "pending"
        assert draft.scheduled_post.caption == "Edited caption"

        campaign.refresh_from_db()
        assert campaign.status == "active"
        campaign.blog_post.refresh_from_db()
        assert campaign.blog_post.promo_count == 1
        assert campaign.blog_post.last_promoted_at is not None

    def test_approve_blocked_without_delivery_target(self, client, campaign):
        draft = self._make_draft(campaign, with_account=False)
        client.force_login(campaign.user)
        client.post(f"/campaigns/drafts/{draft.id}/approve/")
        draft.scheduled_post.refresh_from_db()
        assert draft.scheduled_post.status == "draft"

    def test_approve_blocked_when_caption_exceeds_limit(self, client, campaign):
        draft = self._make_draft(campaign)
        client.force_login(campaign.user)
        client.post(
            f"/campaigns/drafts/{draft.id}/approve/", {"caption": "x" * 600}
        )
        draft.scheduled_post.refresh_from_db()
        assert draft.scheduled_post.status == "draft"
        assert draft.scheduled_post.caption == "x" * 600  # edit kept

    def test_discard_deletes_post(self, client, campaign):
        draft = self._make_draft(campaign)
        client.force_login(campaign.user)
        client.post(f"/campaigns/drafts/{draft.id}/discard/")
        assert not ScheduledPost.objects.filter(id=draft.scheduled_post_id).exists()

    def test_other_users_cannot_touch_drafts(self, client, campaign):
        draft = self._make_draft(campaign)
        other = get_user_model().objects.create_user(email="other@example.com", password="x")
        client.force_login(other)
        resp = client.post(f"/campaigns/drafts/{draft.id}/approve/")
        assert resp.status_code == 404
        draft.scheduled_post.refresh_from_db()
        assert draft.scheduled_post.status == "draft"
