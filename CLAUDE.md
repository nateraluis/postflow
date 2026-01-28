# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PostFlow is a Django 5.2.3 social media scheduling application that allows users to schedule posts to Mastodon/Pixelfed and Instagram Business accounts. The application features:

- Custom user model using email authentication (no username)
- Social media integration (Mastodon.py, Instagram Business API, Facebook Graph API)
- Image scheduling with S3 storage and signed URLs for private media
- Tag and hashtag group management
- Timezone-aware post scheduling
- Stripe integration for subscriptions
- Docker deployment on AWS EC2 with nginx reverse proxy and Let's Encrypt SSL

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
uv run manage.py run_scheduler           # Start APScheduler (runs in production automatically)

# Manual job execution (for testing)
uv run manage.py run_post_scheduled      # Manually process scheduled posts
uv run manage.py refresh_instagram_tokens  # Manually refresh Instagram tokens
```

### Tailwind CSS
```bash
# Development (watch mode)
uv run manage.py tailwind start

# Production build
ur run manage.py tailwind build
```

### Docker (Production)
```bash
# Build and start containers
docker-compose up --build -d

# View logs
docker-compose logs -f django
docker-compose logs -f nginx

# Check scheduler status
docker exec postflow_django pgrep -f "manage.py run_scheduler"  # Should return PID if running
docker-compose logs django | grep -i "scheduler"  # View scheduler logs
```

## Architecture Overview

### Core Django Structure
- **postflow/** - Main Django app containing core functionality
- **subscriptions/** - Subscription management (basic structure, unused models)
- **analytics/** - Post analytics tracking and dashboard
- **theme/** - Tailwind CSS integration with django-tailwind
- **core/** - Django project settings and configuration

### Key Models
- **CustomUser** - Email-based authentication (no username field)
- **ScheduledPost** - Posts with timezone-aware scheduling, supports multiple social platforms
- **MastodonAccount** - OAuth-connected Mastodon/Pixelfed accounts
- **InstagramBusinessAccount** - Instagram Business API integration with token refresh
- **Tag/TagGroup** - Hashtag management system
- **Subscriber** - Email subscriber model

### Storage Configuration
The app uses a dual storage setup:
- **Development (DEBUG=True)**: Local filesystem storage
- **Production (DEBUG=False)**: AWS S3 with separate buckets for static files and private media
  - Static files: Public S3 bucket via `S3StaticStorage`
  - Media files: Private S3 bucket via `S3Boto3Storage` with signed URLs

### Social Media Integration
- **Pixelfed**: Uses pixelfed API endpoints with OAuth tokens
- **Instagram Business**: Uses Facebook Graph API with page access tokens that auto-refresh
- **Scheduling**: Timezone-aware with APScheduler processing posts every minute and refreshing tokens every 6 hours

### Task Scheduling (APScheduler)
PostFlow uses **APScheduler** (not system cron) for reliable task scheduling:
- **Scheduler Module**: `postflow/scheduler.py` - Background scheduler with file locking
- **Auto-Start**: Scheduler launches automatically in `entrypoint.sh` on container startup
- **Jobs**:
  - `post_scheduled`: Runs every minute to process pending posts
  - `refresh_instagram_tokens`: Runs every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
  - `fetch_analytics`: Runs every 6 hours (01:00, 07:00, 13:00, 19:00 UTC) to fetch post engagement metrics
- **Lock File**: `/tmp/postflow_scheduler.lock` prevents duplicate instances
- **Logging**: All scheduler activity logs to Django's `postflow` logger
- **Health Check**: Docker monitors scheduler process; restarts container if it dies
- **Documentation**: See `docs/scheduler.md` for complete details

### Analytics Module
PostFlow uses a **platform-independent analytics architecture** built on Django 6.0 with django-tasks:

#### Pixelfed Analytics (`analytics_pixelfed/`)
- **Architecture**: Fetches ALL posts with media from connected Pixelfed accounts (not just PostFlow-created posts)
- **Models**:
  - `PixelfedPost`: Stores post metadata independently of ScheduledPost
  - `PixelfedLike`: Individual likes with timestamps and usernames
  - `PixelfedComment`: Comments with threading support (in_reply_to_id)
  - `PixelfedShare`: Share/boost tracking
  - `PixelfedEngagementSummary`: Cached metrics for fast dashboard queries
- **API Client** (`pixelfed_client.py`): Robust Pixelfed API integration with retry logic and rate limiting
- **Fetcher Service** (`fetcher.py`): `PixelfedAnalyticsFetcher` class for syncing posts and fetching engagement
- **Background Tasks** (django-tasks):
  - `fetch_all_pixelfed_engagement()`: Hourly engagement fetching (likes, comments, shares)
  - `sync_all_pixelfed_posts()`: Daily post syncing from Pixelfed
- **Management Commands**:
  - `uv run manage.py sync_pixelfed_posts --account-id <id> --limit 50`
  - `uv run manage.py fetch_pixelfed_engagement --account-id <id> --post-id <id> --limit 20`
- **Dashboard**: View at `/analytics/pixelfed/` with engagement timelines and top posts
- **Manual Actions**: Refresh individual posts or sync entire accounts via AJAX endpoints

#### Legacy Analytics Module (`analytics/`)
- **Status**: Deprecated and removed in favor of platform-specific apps
- Old PostAnalytics model has been removed
- Views and templates cleared for future cross-platform dashboard

#### Django 6.0 Background Tasks
- **Framework**: Using Django 6.0's built-in tasks with django-tasks database backend
- **Configuration**: `TASKS` setting in `core/settings.py` with DatabaseBackend
- **Task Execution**: Tasks stored in PostgreSQL and executed via worker process
- **Management**: `uv run python manage.py db_worker` to start task worker (future)

## Testing
- Use pytest for all tests (not Django's unittest)
- Test files go in app-specific tests/ directories (e.g., `postflow/tests/`)
- Use pytest fixtures instead of Django's TestCase
- Run tests before committing changes
- Aim for high test coverage on new code

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

# Run specific test class
uv run pytest postflow/tests/test_scheduler.py::TestSchedulerLock

# Run specific test function
uv run pytest postflow/tests/test_scheduler.py::TestSchedulerLock::test_acquire_lock_success
```

## Frontend development
- Tailwind CSS integrated via django-tailwind
- HTMX used for dynamic frontend interactions
- Avoid using JavaScript unless absolutely necessary

## Database

- Always create migrations for model changes
- Use factory-boy for test data generation
- Be careful with data migrations in production

## Important Conventions

- Environment-specific settings in config/settings/
- Use django-environ for environment variables
- Follow Django best practices and conventions
- Keep security in mind (never commit secrets)

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

# Database (PostgreSQL)
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

### Production Deployment
- Deployed on AWS EC2 via GitHub Actions on push to `main` branch
- Uses Docker Compose with Django + nginx + certbot setup
- **Dependency Management**: Uses `uv` for fast, reliable dependency installation (migrated from pip/requirements.txt)
- Dependencies defined in `pyproject.toml` with locked versions in `uv.lock`
- SSL certificates managed via Let's Encrypt with automatic renewal
- Environment variables injected via GitHub Secrets during deployment

### Docker Configuration
- **Dockerfile**: Uses `uv sync --frozen --no-dev --system` to install dependencies
- Copies `pyproject.toml` and `uv.lock` for reproducible builds
- Installs packages directly into system Python for production use

### GitHub Actions Workflow
- Builds Docker containers on EC2
- Deploys with zero-downtime using container health checks
- Manages SSL certificate renewal via certbot-renewer service
- Includes watchdog service for container monitoring

## Common Development Patterns

### Working with Social Media APIs
- Mastodon accounts use OAuth with stored access tokens
- Instagram accounts require page-level access tokens that expire and auto-refresh
- Use `get_image_file()` method on ScheduledPost to handle S3/local file access

### Database Queries
- Custom user model uses email as USERNAME_FIELD
- All user-related models include user foreign keys with proper related_names
- Timezone handling via pytz with user-specific timezone storage

### Static/Media Files
- Tailwind builds to `theme/static/css/dist/styles.css`
- Development uses STATICFILES_DIRS for multiple static directories
- Production serves static files directly from S3, media files via signed URLs
