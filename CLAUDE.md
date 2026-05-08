# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PostFlow is a Django 6.0.5 social media scheduling application that allows users to schedule posts to Mastodon/Pixelfed and Instagram Business accounts. The application features:

- Custom user model using email authentication (no username)
- Social media integration (Mastodon.py, Instagram Business API, Facebook Graph API)
- Image scheduling with S3 storage and signed URLs for private media
- Tag and hashtag group management with platform-aware limits
- Timezone-aware post scheduling with optimal time suggestions
- Fediverse-native features: CW/spoiler text, visibility controls, thread scheduling, poll scheduling, boost scheduling, RSS-to-fediverse
- Comprehensive analytics: 14+ dashboards across all platforms
- Stripe integration for subscriptions
- systemd deployment on AWS EC2 with nginx (uwsgi_pass) and Let's Encrypt SSL
- PWA with offline support via service worker

## Development Commands

### Local Development
```bash
# Start development server
uv run manage.py runserver

# Database operations
uv run manage.py makemigrations
uv run manage.py migrate

# Static files
uv run manage.py collectstatic

# Scheduler commands
uv run manage.py run_scheduler           # Start APScheduler (runs in production as systemd service)

# Manual job execution (for testing)
uv run manage.py run_post_scheduled      # Manually process scheduled posts
uv run manage.py refresh_instagram_tokens  # Manually refresh Instagram tokens
uv run manage.py snapshot_followers       # Manually snapshot follower counts
uv run manage.py poll_rss_feeds           # Manually poll RSS feeds
```

### Tailwind CSS
```bash
# Development (watch mode)
uv run manage.py tailwind start

# Production build
uv run manage.py tailwind build
```

## Architecture Overview

### Core Django Structure
- **postflow/** - Main Django app containing core functionality
- **subscriptions/** - Subscription management (Stripe)
- **analytics/** - Cross-platform analytics dashboards and utilities
- **analytics_pixelfed/** - Pixelfed-specific analytics
- **analytics_mastodon/** - Mastodon-specific analytics
- **analytics_instagram/** - Instagram-specific analytics
- **theme/** - Tailwind CSS integration with django-tailwind
- **core/** - Django project settings and configuration

### Key Models
- **CustomUser** - Email-based authentication (no username field)
- **ScheduledPost** - Posts with timezone-aware scheduling, supports multiple social platforms, fediverse fields (spoiler_text, visibility, language), poll support, auto-delete TTL, thread chaining
- **ScheduledThread** - Groups multiple ScheduledPosts into connected reply chains
- **ScheduledBoost** - Scheduled reblogs/boosts of other users' posts
- **PostImage** - Multi-image support with per-slide alt text
- **MastodonAccount** - OAuth-connected Mastodon/Pixelfed accounts
- **InstagramBusinessAccount** - Instagram Business API integration with token refresh
- **Tag/TagGroup** - Hashtag management (stored without # prefix, normalized on save)
- **Location** - Saved locations for Instagram location tagging
- **UserTag/DefaultTag** - User/account tagging per image or post
- **CaptionTemplate** - Reusable caption structures with placeholders
- **UserDefaults** - Per-user default hashtag groups, accounts, location
- **FollowerSnapshot** - Daily follower/following/post count snapshots
- **RSSFeed** - RSS feeds for auto-posting new entries
- **HashtagUsage** - Tracks hashtag usage for rotation and analytics

### Publishing Pipeline
- **PostPayload** (`postflow/payload.py`) - Centralized dataclass assembling caption, hashtags, alt text, location, tags, collaborators, CW, visibility, language, poll data
- **build_payload()** - Builds PostPayload from ScheduledPost, called once per post in cron.py
- **Platform utils** receive PostPayload and map to platform-specific API params:
  - `pixelfed/utils.py` - Mastodon-compatible API with support for spoiler_text, visibility, language, polls, in_reply_to_id
  - `mastodon_native/utils.py` - Mastodon.py library with same fediverse features
  - `instagram/utils.py` - Facebook Graph API (fediverse fields silently ignored)
- **Hashtag utils** (`postflow/hashtag_utils.py`) - Banned hashtag checking, platform-aware selection (Instagram 5-tag limit), rotation logic

### Storage Configuration
The app uses a dual storage setup:
- **Development (DEBUG=True)**: Local filesystem storage
- **Production (DEBUG=False)**: AWS S3 with separate buckets for static files and private media
  - Static files: Public S3 bucket via `S3StaticStorage`
  - Media files: Private S3 bucket via `S3Boto3Storage` with signed URLs

### Social Media Integration
- **Pixelfed**: Uses Mastodon-compatible API endpoints with OAuth tokens
- **Mastodon**: Uses Mastodon.py library with full fediverse support (CW, visibility, polls, threads)
- **Instagram Business**: Uses Facebook Graph API with page access tokens that auto-refresh
- **Cross-platform**: All features designed for graceful degradation (fediverse features ignored on Instagram, Instagram-only features skipped on Mastodon/Pixelfed)

### Task Scheduling (APScheduler)
PostFlow uses **APScheduler** for reliable task scheduling, running as a dedicated systemd service:
- **Scheduler Module**: `postflow/scheduler.py` - Background scheduler with file locking
- **systemd Service**: `postflow-scheduler.service` - Runs independently, auto-restarts
- **Jobs**:
  - `post_scheduled`: Every minute - processes pending posts, threads, boosts, and auto-deletes
  - `refresh_instagram_tokens`: Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
  - `sync_pixelfed_posts`: Every hour at :15
  - `fetch_pixelfed_engagement`: Every hour at :45
  - `sync_instagram_posts`: Every hour at :30
  - `fetch_instagram_insights`: Every 2 hours at :20
  - `sync_mastodon_posts`: Every hour at :35
  - `fetch_mastodon_engagement`: Every 2 hours at :50
  - `snapshot_followers`: Daily at 06:00 UTC
  - `poll_rss_feeds`: Every 30 minutes
- **Lock File**: `/tmp/postflow_scheduler.lock` prevents duplicate instances
- **Logging**: Scheduler logs to `/var/log/postflow/scheduler.log`

### Analytics Module
PostFlow has a comprehensive analytics suite with 14+ dashboards:

#### Cross-Platform Analytics (`analytics/`)
- **Best Time to Post**: Heatmap by day/hour with benchmark fallback
- **Engagement Timeline**: Stacked bars with daily/weekly/monthly aggregation, CSV export
- **Engagement Velocity**: First 24/48/72h engagement speed
- **Engagement Decay**: Long-tail content detection
- **Media Type Performance**: Image/video/carousel comparison
- **Hashtag Performance**: Group-level engagement correlation
- **Top Performers**: Best posts by engagement
- **Consistency Score**: 0-100 posting regularity gauge
- **Engagement Quality**: Weighted scoring (comments 3x, shares 2x, likes 1x)
- **Growth Momentum**: Week-over-week engagement trends
- **Viral Coefficient**: Shares-to-likes ratio tracking
- **Content Themes**: Hashtag cloud with engagement-colored sizing
- **Community Conversations**: Expandable thread cards with comment chains
- **Comment Inbox**: Unified comments across platforms with quick-reply
- **Trending Hashtags**: Live trending data from connected instances
- **Follower Growth**: Daily snapshots with growth charts
- **Weekly Digest**: Online summary at /digest/

#### Platform-Specific Analytics
- **Pixelfed** (`analytics_pixelfed/`): Full engagement tracking with likes, comments, shares
- **Mastodon** (`analytics_mastodon/`): Favourites, replies, reblogs tracking
- **Instagram** (`analytics_instagram/`): Likes, comments, saves, reach, impressions

## Testing
- Use pytest for all tests (not Django's unittest)
- Test files go in app-specific tests/ directories (e.g., `postflow/tests/`)
- Use pytest fixtures instead of Django's TestCase
- Run tests before committing changes

### Running Tests
```bash
# Install test dependencies
uv sync --extra test

# Run all tests
uv run pytest

# Run specific test file
uv run pytest postflow/tests/test_scheduler.py

# Run with coverage
uv run pytest --cov=postflow --cov-report=html
```

## Frontend Development
- Tailwind CSS integrated via django-tailwind
- HTMX used for dynamic frontend interactions
- Alpine.js bundled locally for interactive components (thread composer, conversation expand/collapse)
- Avoid using JavaScript unless absolutely necessary
- PWA with service worker (`postflow/static/postflow/serviceworker.js`) for offline caching
- All views must be mobile-friendly and work in PWA standalone mode

## Database

- Always create migrations for model changes
- Use factory-boy for test data generation
- Be careful with data migrations in production
- Hashtags stored without # prefix (normalized on save via Tag.save())

## Important Conventions

- Environment-specific settings in core/settings.py via django-environ
- Follow Django best practices and conventions
- Keep security in mind (never commit secrets)
- No AI functionalities or video features
- Cross-platform compatibility: fediverse features degrade gracefully on Instagram
- PostPayload dataclass centralizes all publishing logic

## Git Workflow
- Use feature branches for new work
- Pull requests must be reviewed before merging
- Write clear commit messages
- Test thoroughly before pushing changes
- Use conventional commits if possible

## Environment Configuration

### Required Environment Variables (core/.env)
```env
DJANGO_SECRET_KEY=your_secret_key
DEBUG=True  # False for production

# Database (PostgreSQL on RDS)
DB_NAME=postflow
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# AWS S3 Storage
S3_ACCESS_KEY=your_s3_key
S3_SECRET_KEY=your_s3_secret
S3_AWS_STORAGE_BUCKET_NAME=your_static_bucket
AWS_STORAGE_MEDIA_BUCKET_NAME=your_media_bucket
MEDIA_ACCESS_KEY=your_media_key
MEDIA_SECRET_ACCESS_KEY=your_media_secret

# Social Media APIs
FACEBOOK_APP_ID=your_app_id
FACEBOOK_APP_SECRET=your_app_secret
FACEBOOK_VERIFY_TOKEN=your_verify_token
INSTAGRAM_BUSINESS_REDIRECT_URI=your_redirect_uri
REDIRECT_URI=http://localhost:8000/mastodon/callback  # Mastodon OAuth
```

## Deployment

### Production Stack
- **Server**: AWS EC2 (Ubuntu 24.04), Python 3.13, uv
- **Web server**: nginx with native `uwsgi_pass` to uwsgi on 127.0.0.1:8000
- **App server**: uwsgi (2 processes, 2 threads) managed by systemd
- **Scheduler**: APScheduler as a separate systemd service
- **SSL**: Let's Encrypt via system certbot with auto-renewal timer
- **Static files**: Uploaded to S3 via collectstatic, served by nginx proxy to S3
- **Media files**: Private S3 bucket with signed URLs

### systemd Services
```
postflow.target                    # Groups all PostFlow services
├── postflow-web.service           # uwsgi web server
└── postflow-scheduler.service     # APScheduler background jobs
```

Service files are in `systemd/` directory and installed to `/etc/systemd/system/` during deploy.

### Server Management
```bash
# SSH to server
ssh -i ~/.ssh/postflow.pem ubuntu@3.74.49.26

# Check service status
sudo systemctl status postflow.target
sudo systemctl status postflow-web.service
sudo systemctl status postflow-scheduler.service

# Restart services
sudo systemctl restart postflow.target

# View logs
tail -f /var/log/postflow/uwsgi.log       # Django/uwsgi logs
tail -f /var/log/postflow/scheduler.log    # Scheduler logs

# nginx
sudo systemctl status nginx
sudo nginx -t && sudo systemctl reload nginx
```

### GitHub Actions Workflow
Deployment triggers on push to `main` branch (`.github/workflows/deploy.yml`):
1. Uploads `.env` from GitHub Secrets
2. SSHes to EC2: `git fetch && git reset --hard origin/main`
3. `uv sync --frozen --no-dev`
4. Tailwind build: `npm ci && manage.py tailwind build`
5. `manage.py migrate --noinput`
6. `manage.py collectstatic --noinput`
7. Installs systemd service files and nginx config
8. `systemctl restart postflow.target`
9. `nginx -t && systemctl restart nginx`
10. Verifies all services are active

### nginx Configuration
- Config file: `deploy/nginx-postflow.conf` (installed to `/etc/nginx/sites-available/postflow`)
- Uses `uwsgi_pass 127.0.0.1:8000` (native uwsgi protocol, no HTTP proxy overhead)
- SSL with TLS 1.2/1.3, HSTS, security headers
- Static files proxied to S3 with caching
- ACME challenge webroot at `/var/www/certbot`

## Common Development Patterns

### Working with Social Media APIs
- Mastodon accounts use OAuth with stored access tokens
- Instagram accounts require page-level access tokens that expire and auto-refresh
- Use `get_image_file()` method on ScheduledPost to handle S3/local file access
- All publishing goes through PostPayload for consistent cross-platform behavior

### Database Queries
- Custom user model uses email as USERNAME_FIELD
- All user-related models include user foreign keys with proper related_names
- Timezone handling via pytz with user-specific timezone storage

### Static/Media Files
- Tailwind builds to `theme/static/css/dist/styles.css`
- Development uses STATICFILES_DIRS for multiple static directories
- Production serves static files directly from S3, media files via signed URLs
