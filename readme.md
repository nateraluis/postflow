# PostFlow

PostFlow is a website-to-social control centre at https://postflow.photo. A user connects a website, PostFlow ingests its content and images, AI drafts platform-specific social posts in the author's own voice, the user approves them from a review queue, a scheduler publishes them, and weekly AI reports evaluate whether the campaign is driving visitors and newsletter subscribers.

## How it fits together

```
Website (any URL)
  └─ websites/        ingest posts + images (Ghost Content API / Ghost GEO / RSS / sitemap crawl)
       └─ campaigns/  AI drafts per platform (Claude) → review queue → approve
            └─ postflow/  ScheduledPost + APScheduler cron publishes approved posts
                 ├─ pixelfed/, mastodon_native/, instagram/   existing connectors
                 ├─ linkedin/, threads/                        API connectors
                 └─ glass/                                     manual queue (no public API)
  └─ analytics_site/  per-website analytics (Plausible, Search Console, Ghost members)
       └─ campaigns/evaluator.py  weekly Claude report + recommendations
```

Nothing AI-generated ever posts without approval: drafts are created with `status="draft"`; only `status="pending"` posts are picked up by the publisher (`postflow/cron.py`).

## Apps

| App | Purpose |
|---|---|
| `postflow` | Users, composer, `ScheduledPost`, calendar, scheduler (`scheduler.py`), publisher (`cron.py`) |
| `websites` | Connected websites, pluggable content-source adapters (`websites/sources/`), content library |
| `campaigns` | Voice profiles, AI drafting (`ai.py`), UTM tagging (`utm.py`), slot planner, review queue, weekly evaluator (`evaluator.py`) |
| `pixelfed`, `mastodon_native`, `instagram`, `linkedin`, `threads` | Platform OAuth + posting utils |
| `glass` | Manual posting queue for Glass (no public API) |
| `analytics`, `analytics_pixelfed`, `analytics_mastodon`, `analytics_instagram` | Social engagement analytics |
| `analytics_site` | Website analytics: provider collectors, daily `SiteSnapshot`s, UTM attribution, post-impact dashboard |
| `subscriptions` | Stripe gating (`SUBSCRIPTION_EXEMPT_EMAILS` bypasses it for owner accounts) |

## Scheduler jobs (systemd `postflow-scheduler`)

| Job | Cadence |
|---|---|
| `post_scheduled` | every minute |
| `refresh_instagram_tokens` / `refresh_threads_tokens` | every 6 h |
| `sync_*_posts`, `fetch_*_engagement` | hourly / 2-hourly |
| `snapshot_followers` | daily 06:00 UTC |
| `poll_rss_feeds` | every 30 min |
| `sync_website_content` | every 6 h |
| `collect_site_analytics` | daily 07:30 UTC |
| `generate_campaign_reports` | Mondays 07:45 UTC |

## Development

Requirements: Python 3.13, uv, PostgreSQL, Node 22 (Tailwind).

```bash
cp .env.example core/.env   # fill in values
uv sync --extra test
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest               # full test suite
```

Useful commands:

```bash
uv run python manage.py sync_website_content [--website ID]
uv run python manage.py collect_site_analytics [--website ID]
uv run python manage.py import_photo_analytics --website ID [--file path/to/analytics.db]
uv run python manage.py generate_campaign_report [--user-id ID]
uv run python manage.py run_scheduler
```

## Configuration

All settings come from `core/.env` — see `.env.example` for the full list. Notable:

- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL_DRAFTING`, `ANTHROPIC_MODEL_ANALYSIS` — the AI layer.
- `FIELD_ENCRYPTION_KEY` — Fernet key encrypting platform tokens and analytics credentials at rest (`core/fields.py`). Legacy plaintext rows stay readable and are encrypted on their next save. Losing the key means reconnecting every account.
- `SUBSCRIPTION_EXEMPT_EMAILS` — owner accounts that bypass Stripe.
- `LINKEDIN_*`, `THREADS_*`, `FACEBOOK_*` — platform app credentials.

## Deployment

Pushing to `main` triggers `.github/workflows/deploy.yml`: it writes `core/.env` from GitHub Actions secrets, SSHes to the EC2 host, pulls, `uv sync`, builds Tailwind, migrates, collects static, and restarts the systemd units (`postflow-web`, `postflow-scheduler`). Nginx fronts uWSGI; certbot handles TLS.

New secrets must be added both to GitHub Actions secrets *and* to the `.env` block in `deploy.yml`.
