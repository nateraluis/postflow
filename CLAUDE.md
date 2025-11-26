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
PostFlow tracks engagement metrics for published posts across all platforms:
- **Models**: `PostAnalytics` - Stores likes, comments, shares, impressions, reach
- **API Integration**: Fetches data from Instagram Graph API, Mastodon API, Pixelfed API
- **Auto-Collection**: Scheduled job runs every 6 hours to fetch latest analytics
- **Dashboard**: View post performance at `/analytics/` with filters by platform
- **Manual Refresh**: Users can trigger on-demand analytics refresh
- **Platform-Specific Metrics**:
  - Instagram: likes, comments, impressions, reach, saved
  - Mastodon: favorites, replies, reblogs
  - Pixelfed: favorites, replies, shares
- **Management Command**: `python manage.py fetch_analytics` for manual fetching

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
- SSL certificates managed via Let's Encrypt with automatic renewal
- Environment variables injected via GitHub Secrets during deployment

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
